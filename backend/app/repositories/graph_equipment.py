"""
Equipment repository backed by Microsoft Graph SharePoint List.
Column mapping is discovered dynamically from list metadata.
"""
from app.repositories.base import EquipmentRepository
from app.models.equipment import EquipmentModel
from app.repositories.graph_client import GraphClient, GraphError
from app.core.config import settings

class GraphEquipmentRepository(EquipmentRepository):
    def __init__(self, client: GraphClient):
        self.client = client
        self.site_id = settings.MICROSOFT_SITE_ID
        self.list_id = settings.MICROSOFT_EQUIPMENT_LIST_ID
        self.col_map = self._discover_columns()
        
    def _discover_columns(self) -> dict:
        try:
            path = f"/sites/{self.site_id}/lists/{self.list_id}/columns"
            data = self.client.get_all_pages(path)
            mapping = {}
            for col in data:
                display = col.get("displayName")
                name = col.get("name")
                if display in ["EquipmentID", "EquipmentName", "Category", "Description", "Quantity", "Unit", "Location"]:
                    mapping[display] = name
            return mapping
        except GraphError:
            return {}

    def _map_to_model(self, item: dict) -> EquipmentModel | None:
        fields = item.get("fields", {})
        
        eq_id = fields.get(self.col_map.get("EquipmentID"))
        name = fields.get(self.col_map.get("EquipmentName"))
        
        if not eq_id or not name:
            return None
            
        qty = fields.get(self.col_map.get("Quantity"), 0)
        try:
            qty = int(qty)
        except (ValueError, TypeError):
            qty = 0
            
        return EquipmentModel(
            equipment_id=str(eq_id),
            equipment_name=str(name),
            category=fields.get(self.col_map.get("Category")),
            description=fields.get(self.col_map.get("Description")),
            quantity_total=qty,
            unit=fields.get(self.col_map.get("Unit")),
            location=fields.get(self.col_map.get("Location"))
        )

    def get_all(self) -> list[EquipmentModel]:
        path = f"/sites/{self.site_id}/lists/{self.list_id}/items?expand=fields"
        items = self.client.get_all_pages(path)
        
        models = []
        for item in items:
            model = self._map_to_model(item)
            if model:
                models.append(model)
        return models

    def get_by_id(self, equipment_id: str) -> EquipmentModel | None:
        all_items = self.get_all()
        for item in all_items:
            if item.equipment_id == equipment_id:
                return item
        return None

    def search(self, query: str) -> list[EquipmentModel]:
        all_items = self.get_all()
        if not query:
            return all_items
            
        query = query.lower()
        results = []
        for item in all_items:
            if query in item.equipment_name.lower() or (item.description and query in item.description.lower()) or (item.category and query in item.category.lower()):
                results.append(item)
        return results

    def count(self) -> int:
        return len(self.get_all())

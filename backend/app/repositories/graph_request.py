"""
EquipmentRequest repository backed by Microsoft Graph SharePoint List.
"""
from datetime import datetime
from app.repositories.base import RequestRepository
from app.models.request import RequestModel
from app.schemas.requests import RequestStatus
from app.repositories.graph_client import GraphClient, GraphError
from app.core.config import settings

class GraphRequestRepository(RequestRepository):
    def __init__(self, client: GraphClient):
        self.client = client
        self.site_id = settings.MICROSOFT_SITE_ID
        self.list_id = settings.MICROSOFT_REQUESTS_LIST_ID
        self.col_map = self._discover_columns()
        
    def _discover_columns(self) -> dict:
        try:
            path = f"/sites/{self.site_id}/lists/{self.list_id}/columns"
            data = self.client.get_all_pages(path)
            mapping = {}
            expected_cols = ["RequesterEmail", "RequesterName", "Project", "EquipmentID", "EquipmentName", "Quantity", "NeededFrom", "NeededTo", "Purpose", "PriorityLevel", "PriorityReason", "Status", "Title"]
            for col in data:
                display = col.get("displayName")
                name = col.get("name")
                if display in expected_cols:
                    mapping[display] = name
            return mapping
        except GraphError:
            return {}

    def _map_to_model(self, item: dict) -> RequestModel | None:
        fields = item.get("fields", {})
        try:
            req_id = int(fields.get("id", item.get("id")))
        except (ValueError, TypeError):
            return None
            
        def parse_date(d_str):
            if not d_str:
                return None
            try:
                # Graph usually returns ISO format with Z
                return datetime.fromisoformat(d_str.replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    return datetime.strptime(d_str.split("T")[0], "%Y-%m-%d").date()
                except ValueError:
                    return None
            
        return RequestModel(
            id=req_id,
            requester_email=fields.get(self.col_map.get("RequesterEmail", "")),
            requester_name=fields.get(self.col_map.get("RequesterName", "")),
            project=fields.get(self.col_map.get("Project", "")),
            equipment_id=fields.get(self.col_map.get("EquipmentID", "")),
            equipment_name=fields.get(self.col_map.get("EquipmentName", "")),
            quantity=int(fields.get(self.col_map.get("Quantity", 0)) or 0),
            needed_from=parse_date(fields.get(self.col_map.get("NeededFrom", ""))),
            needed_to=parse_date(fields.get(self.col_map.get("NeededTo", ""))),
            purpose=fields.get(self.col_map.get("Purpose", "")),
            priority_level=fields.get(self.col_map.get("PriorityLevel", "")),
            priority_reason=fields.get(self.col_map.get("PriorityReason", "")),
            status=fields.get(self.col_map.get("Status", RequestStatus.PENDING)),
            created_at=datetime.utcnow() # Approximation
        )

    def _map_to_fields(self, model: RequestModel) -> dict:
        fields = {}
        if "RequesterEmail" in self.col_map: fields[self.col_map["RequesterEmail"]] = model.requester_email
        if "RequesterName" in self.col_map: fields[self.col_map["RequesterName"]] = model.requester_name
        if "Project" in self.col_map: fields[self.col_map["Project"]] = model.project
        if "EquipmentID" in self.col_map: fields[self.col_map["EquipmentID"]] = model.equipment_id
        if "EquipmentName" in self.col_map: fields[self.col_map["EquipmentName"]] = model.equipment_name
        if "Quantity" in self.col_map: fields[self.col_map["Quantity"]] = model.quantity
        if "NeededFrom" in self.col_map and model.needed_from: fields[self.col_map["NeededFrom"]] = model.needed_from.isoformat()
        if "NeededTo" in self.col_map and model.needed_to: fields[self.col_map["NeededTo"]] = model.needed_to.isoformat()
        if "Purpose" in self.col_map: fields[self.col_map["Purpose"]] = model.purpose
        if "PriorityLevel" in self.col_map: fields[self.col_map["PriorityLevel"]] = model.priority_level
        if "PriorityReason" in self.col_map: fields[self.col_map["PriorityReason"]] = model.priority_reason
        if "Status" in self.col_map: fields[self.col_map["Status"]] = model.status
        return fields

    def create(self, model: RequestModel) -> RequestModel:
        fields = self._map_to_fields(model)
        payload = {"fields": fields}
        path = f"/sites/{self.site_id}/lists/{self.list_id}/items"
        res = self.client.post(path, payload)
        
        item_id = res.get("id")
        title = f"REQ-{item_id}"
        if "Title" in self.col_map:
            update_path = f"/sites/{self.site_id}/lists/{self.list_id}/items/{item_id}/fields"
            self.client.patch(update_path, {self.col_map["Title"]: title})
            
        return self.get_by_id(int(item_id))

    def get_by_id(self, id: int) -> RequestModel | None:
        path = f"/sites/{self.site_id}/lists/{self.list_id}/items/{id}?expand=fields"
        try:
            res = self.client.get(path)
            return self._map_to_model(res)
        except GraphError as e:
            if e.status_code == 404:
                return None
            raise

    def update(self, model: RequestModel) -> RequestModel:
        fields = self._map_to_fields(model)
        path = f"/sites/{self.site_id}/lists/{self.list_id}/items/{model.id}/fields"
        self.client.patch(path, fields)
        return self.get_by_id(model.id)

    def list_by_requester(self, email: str) -> list[RequestModel]:
        all_reqs = self.list_all()
        return [r for r in all_reqs if r.requester_email and r.requester_email.lower() == email.lower()]

    def list_all(self, status: RequestStatus | None = None) -> list[RequestModel]:
        path = f"/sites/{self.site_id}/lists/{self.list_id}/items?expand=fields"
        items = self.client.get_all_pages(path)
        
        models = []
        for item in items:
            m = self._map_to_model(item)
            if m:
                if status and m.status != status:
                    continue
                models.append(m)
        return models

    def get_overlapping(self, equipment_id: str, needed_from, needed_to, statuses: list[RequestStatus], exclude_id: int | None = None) -> list[RequestModel]:
        all_reqs = self.list_all()
        overlapping = []
        for r in all_reqs:
            if r.equipment_id != equipment_id:
                continue
            if r.status not in statuses:
                continue
            if exclude_id is not None and r.id == exclude_id:
                continue
                
            if r.needed_from <= needed_to and r.needed_to >= needed_from:
                overlapping.append(r)
        return overlapping

    def count_by_status(self) -> dict[str, int]:
        all_reqs = self.list_all()
        counts = {}
        for r in all_reqs:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts

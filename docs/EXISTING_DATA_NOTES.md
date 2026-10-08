# Notes about existing data and Lists

## Existing Equipment source

The user has already imported the equipment CSV into a Microsoft List named `Equipment`. Expected fields for V1:
- `EquipmentID`
- `EquipmentName`
- `Category`
- `Description`
- `Quantity`
- `Unit`
- `Location`

The user removed or decided not to use `Target`. Verify the actual List columns before implementing any Microsoft Lists mapping. Do not assume the imported columns perfectly match these names; provide configurable mapping or a clear setup check.

The source workbook `inventory_normalized.xlsx` is not included in this starter pack because it may contain internal equipment information. If permitted, the user can export the `Equipment` List as CSV and copy it to `data/private/equipment.csv` locally. Do not commit that file.

## Existing Projects List

The user may already have a `Projects` List. Do not delete it. V1 does not require it and must not depend on it for priority, because the project information and update process are not yet established. The request form stores the project name as text. A future integration can read confirmed project data if there is an authorized, reliable source.

## Equipment_Requests

Create/configure this List only after confirming where it will live and whether the app can access it. Fields are documented in `DATA_MODEL.md`. Use the built-in Microsoft Lists `ID`, `Created`, and `Modified` columns rather than creating duplicate columns.

## Microsoft Lists connection is not yet verified

The user has been able to create a blank List and import CSV, but API access from an application has not been verified. Do not report the connection as working until a test has actually read an equipment item and created/updated a test request using the configured account and List IDs.

# Microsoft Entra ID and SharePoint Setup Guide

The MVP uses Microsoft Graph API and SharePoint Lists as a production data backend instead of a local SQLite database.

## 1. Prerequisites (Work/School Account Required)
Personal Microsoft accounts (like `@outlook.com` or `@hotmail.com`) **will not work** due to Graph API limitations for SharePoint Lists and Entra ID scopes.
You must use a Microsoft 365 Work or School account (e.g. `@yourcompany.com` or `@youruniversity.edu`).

## 2. Creating a SharePoint Online Site
1. Go to [SharePoint](https://office.com/launch/sharepoint).
2. Click **Create site** > **Team site** or **Communication site**.
3. Name it (e.g., `Equipment Agent DB`).
4. Note the URL.

## 3. Creating the Equipment List
1. In your new site, click **New** > **List** > **Blank list**.
2. Name it exactly `Equipment`.
3. Create the following columns with EXACT display names (Note: `Title` is created by default; we won't use it, or you can rename it to `EquipmentID`, but it's safer to create new columns and ignore `Title`):
   - `EquipmentID` (Single line of text)
   - `EquipmentName` (Single line of text)
   - `Category` (Single line of text)
   - `Description` (Multiple lines of text)
   - `Quantity` (Number)
   - `Unit` (Single line of text)
   - `Location` (Single line of text)

## 4. Creating the Equipment_Requests List
1. Click **New** > **List** > **Blank list**.
2. Name it exactly `Equipment_Requests`.
3. Create the following columns:
   - `RequesterEmail` (Single line of text)
   - `RequesterName` (Single line of text)
   - `Project` (Single line of text)
   - `EquipmentID` (Single line of text)
   - `EquipmentName` (Single line of text)
   - `Quantity` (Number)
   - `NeededFrom` (Date and time)
   - `NeededTo` (Date and time)
   - `Purpose` (Multiple lines of text)
   - `PriorityLevel` (Single line of text)
   - `PriorityReason` (Multiple lines of text)
   - `Status` (Single line of text)
   - `Title` (Single line of text - built-in)

## 5. App Registration in Entra ID
1. Go to the [Entra ID Portal](https://entra.microsoft.com/).
2. Navigate to **Applications** > **App registrations** > **New registration**.
3. Name it (e.g., `AI Equipment Agent`).
4. Supported account types: **Accounts in any organizational directory (Any Microsoft Entra ID tenant - Multitenant)**.
5. Redirect URI: Select **Web**, enter `http://localhost:8000/auth/callback`.
6. Click **Register**.
7. Copy the **Application (client) ID** and **Directory (tenant) ID**.
8. Go to **Certificates & secrets** > **New client secret**. Copy the **Value**.
9. Go to **API permissions** > **Add a permission** > **Microsoft Graph** > **Delegated permissions**.
10. Check: `openid`, `profile`, `offline_access`, `User.Read`, `Sites.ReadWrite.All`.
11. Click **Add permissions**.

## 6. Getting Site ID and List IDs
Use [Graph Explorer](https://developer.microsoft.com/en-us/graph/graph-explorer):
1. **Site ID**: GET `https://graph.microsoft.com/v1.0/sites/{hostname}:/sites/{sitename}`
   - Extract the `id` property.
2. **Equipment List ID**: GET `https://graph.microsoft.com/v1.0/sites/{site-id}/lists`
   - Find the `Equipment` list and extract its `id`.
3. **Requests List ID**: (Same as above for `Equipment_Requests`).

## 7. Configuration (.env)
Copy `.env.example` to `.env` and fill in all the details from the previous steps.
Set `DATA_BACKEND=microsoft_graph`.

## 8. Run Integration Health Check
Start the backend and run:
`curl http://localhost:8000/api/health/integrations`
This will verify connectivity without writing any data.

## 9. Testing End-to-End
1. Go to `http://localhost:5173`.
2. Login with Microsoft.
3. Make a test request and check the SharePoint list to see the created item.

## 10. Clean up
Simply delete the test items from the SharePoint lists.

Workflow for the Attendance System

**Overall Security:**
*   The entire web application is protected by a single HTTP Basic Authentication login. Before any page is visible, the user must provide a shared username and password. This provides a simple but effective security layer for the entire system.

---

#### **1. Home Page (Employee Selection)**
*   **Function:** This is the main landing page after successful login.
*   **Content:**
    *   A clean and simple list of all **active** employee names. Disabled employees will not appear in this list.
    *   Each name is a clickable link that takes the user to their specific Action Page.
    *   A clear link to the "Admin & Reports" page.

---

#### **2. Action Page (Clock In / Clock Out)**
*   **Function:** To record an employee's entry or exit.
*   **Workflow:**
    1.  After an employee clicks their name on the Home Page, they are taken here. The page will prominently display their name to confirm they've selected the right person (e.g., "Welcome, Jane Doe").
    2.  The system checks the database for that employee's last recorded action.
        *   If the last action was "Leave" (or if there are no actions for the day), a single, large **"Enter"** button is displayed.
        *   If the last action was "Enter," a single, large **"Leave"** button is displayed.
    3.  When the button is clicked, the system instantly records the following into the SQLite database:
        *   **Employee Name:** The name of the employee.
        *   **Action:** "Enter" or "Leave".
        *   **Timestamp:** The current date and time, hardcoded to the Central European Time (Prague) timezone.
    4.  A confirmation message appears on the screen (e.g., "Successfully clocked in at 09:01 CET").
    5.  A "Back to Home" button is always visible to return to the employee selection screen.

---

#### **3. Admin & Reports Page**
*   **Function:** To manage employees and export attendance data. This page is accessible from the Home Page and is protected by the same HTTP Basic Auth as the rest of the site.
*   **Content:** This page would be split into two distinct sections:

    **Section A: Attendance Reports & Export**
    *   **Default View:** The page loads showing a table of all attendance records from the **previous full month** (e.g., if it's October, it will show all of September's data).
    *   **Filtering:** Users can adjust the report with:
        *   A date range selector (start date and end date).
        *   A dropdown menu to filter by a specific employee or show all employees.
    *   **Export:** A clearly visible **"Export to CSV"** button. Clicking this will generate and download a CSV file based on the currently selected filters. The CSV columns will be: `Employee Name`, `Status (Enter/Leave)`, `Date`, `Time`.

    **Section B: Employee Management**
    *   **Add New Employee:**
        *   A simple text input field labeled "New Employee Name."
        *   An "Add Employee" button next to it. Clicking this adds the new name to the database as an active employee.
    *   **Manage Existing Employees:**
        *   A list of all employees (both active and disabled) is displayed.
        *   Next to each **active** employee's name is a **"Disable"** button. Clicking this will flag the employee as "inactive" in the database. They will no longer appear on the Home Page, but their past attendance data is kept forever.
        *   Next to each **disabled** employee's name is an **"Enable"** button. Clicking this will make them active again and they will reappear on the Home Page.


import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import datetime
import calendar
import matplotlib.pyplot as plt
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# ---------------- Database Setup ----------------
def init_db():
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    date TEXT NOT NULL
                )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )""")
    conn.commit()
    conn.close()

# ---------------- Expense Operations ----------------
def add_expense(amount, category, description, date):
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    c.execute("INSERT INTO expenses (amount, category, description, date) VALUES (?, ?, ?, ?)",
              (amount, category, description, date))
    conn.commit()
    conn.close()

def delete_expense(expense_id):
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    c.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
    conn.commit()
    conn.close()

def fetch_expenses(filters=None):
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    query = "SELECT * FROM expenses WHERE 1=1"
    params = []

    if filters:
        if filters.get("from_date"):
            query += " AND date >= ?"
            params.append(filters["from_date"])
        if filters.get("to_date"):
            query += " AND date <= ?"
            params.append(filters["to_date"])
        if filters.get("category") and filters["category"] != "All":
            query += " AND category = ?"
            params.append(filters["category"])

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return rows

def get_total_expenses_for_month(year, month):
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM expenses WHERE strftime('%Y-%m', date) = ?",
              (f"{year}-{month:02d}",))
    total = c.fetchone()[0]
    conn.close()
    return total if total else 0

# ---------------- Budget & Settings ----------------
def get_budget():
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='monthly_budget'")
    row = c.fetchone()
    conn.close()
    return float(row[0]) if row else 0

def set_budget(amount):
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('monthly_budget', ?)", (str(amount),))
    conn.commit()
    conn.close()

def set_category_limit(category, amount):
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    key = f"limit_{category}"
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(amount)))
    conn.commit()
    conn.close()

def get_category_limit(category):
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    key = f"limit_{category}"
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return float(row[0]) if row else None

def mark_category_unwanted(category, unwanted=True):
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    key = f"unwanted_{category}"
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, "1" if unwanted else "0"))
    conn.commit()
    conn.close()

def is_category_unwanted(category):
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    key = f"unwanted_{category}"
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row and row[0] == "1"

def set_block_mode(enabled: bool):
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('block_mode', ?)", ( "1" if enabled else "0",))
    conn.commit()
    conn.close()

def get_block_mode() -> bool:
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='block_mode'")
    row = c.fetchone()
    conn.close()
    return row and row[0] == "1"

# ---------------- Helpers & Projections ----------------
def get_month_spent_by_category(year, month, category):
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    c.execute("""SELECT SUM(amount) FROM expenses 
                 WHERE strftime('%Y-%m', date)=? AND category=?""",
              (f"{year}-{month:02d}", category))
    total = c.fetchone()[0]
    conn.close()
    return total if total else 0

def projected_month_end_spend(year, month):
    today = datetime.date.today()
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM expenses WHERE strftime('%Y-%m', date)=?", (f"{year}-{month:02d}",))
    spent = c.fetchone()[0] or 0
    conn.close()
    days_in_month = calendar.monthrange(year, month)[1]
    # If projecting a past month or a different month, use full days_in_month
    if today.year == year and today.month == month:
        day = today.day
    else:
        day = days_in_month
    if day == 0:
        return spent
    projected = (spent / day) * days_in_month
    return projected

def recommend_actions_for_month(year, month):
    budget = get_budget()
    spent = get_total_expenses_for_month(year, month)
    proj = projected_month_end_spend(year, month)
    suggestions = []
    if budget > 0:
        need_to_save = max(0, proj - budget)
    else:
        need_to_save = 0
    if need_to_save > 0:
        suggestions.append(f"Projected overshoot: ₹{need_to_save:.0f}. Try to cut this month by ₹{need_to_save:.0f}.")
        # find top categories by spend
        conn = sqlite3.connect("expenses.db"); c = conn.cursor()
        c.execute("""SELECT category, SUM(amount) FROM expenses WHERE strftime('%Y-%m', date)=?
                     GROUP BY category ORDER BY SUM(amount) DESC LIMIT 5""", (f"{year}-{month:02d}",))
        tops = c.fetchall(); conn.close()
        for cat, amt in tops:
            suggestions.append(f"Top: {cat} — spent ₹{amt:.0f}. Consider cutting 20-40% from {cat}.")
    else:
        suggestions.append("You're on track — projected spending is within budget. Consider adding to savings.")
    # include unwanted-category tips
    # any unwanted category that has spending this month
    conn = sqlite3.connect("expenses.db"); c = conn.cursor()
    c.execute("""SELECT key FROM settings WHERE key LIKE 'unwanted_%' AND value='1'""")
    unwanted_keys = c.fetchall(); conn.close()
    for (k,) in unwanted_keys:
        cat = k.replace("unwanted_", "")
        cat_spent = get_month_spent_by_category(year, month, cat)
        if cat_spent > 0:
            suggestions.append(f"Unwanted category {cat} already has ₹{cat_spent:.0f} this month. Avoid further purchases in this category.")
    return suggestions

# ---------------- Export ----------------
def export_to_excel(expenses, filename):
    wb = Workbook()
    ws = wb.active
    ws.title = "Expenses"
    headers = ["ID", "Amount", "Category", "Description", "Date"]
    ws.append(headers)
    for row in expenses:
        ws.append(row)
    wb.save(filename)

def export_to_pdf(expenses, filename):
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(200, y, "Expense Report")
    y -= 30
    c.setFont("Helvetica", 10)
    headers = ["ID", "Amount", "Category", "Description", "Date"]
    c.drawString(30, y, " | ".join(headers))
    y -= 20
    for row in expenses:
        line = " | ".join([str(x) for x in row])
        c.drawString(30, y, line[:100])
        y -= 15
        if y < 50:
            c.showPage()
            y = height - 50
    c.save()

# ---------------- Reports ----------------
def show_category_pie():
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    today = datetime.date.today()
    c.execute("""SELECT category, SUM(amount) FROM expenses
                 WHERE strftime('%Y-%m', date)=? GROUP BY category""",
              (today.strftime("%Y-%m"),))
    data = c.fetchall()
    conn.close()
    if not data:
        messagebox.showinfo("No Data", "No expenses for this month.")
        return
    labels, values = zip(*data)
    plt.figure(figsize=(6, 6))
    plt.pie(values, labels=labels, autopct="%1.1f%%")
    plt.title("Expenses by Category (This Month)")
    plt.show()

def show_monthly_trend():
    conn = sqlite3.connect("expenses.db")
    c = conn.cursor()
    c.execute("""SELECT strftime('%Y-%m', date) as month, SUM(amount) 
                 FROM expenses GROUP BY month ORDER BY month DESC LIMIT 6""")
    data = c.fetchall()
    conn.close()
    if not data:
        messagebox.showinfo("No Data", "No expense data available.")
        return
    months, totals = zip(*reversed(data))
    plt.figure()
    plt.plot(months, totals, marker="o")
    plt.title("Monthly Expense Trend")
    plt.xlabel("Month")
    plt.ylabel("Total Expenses")
    plt.show()

# ---------------- GUI ----------------
CATEGORIES = ["Food", "Travel", "Shopping", "Bills", "Medical", "Trip", "Dress", "Cosmetics", "JunkFood", "Other"]

class ExpenseTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Expense Tracker")
        self.root.configure(bg="#f0f2f5")
        self.create_widgets()
        # ensure DB exists
        self.refresh_budget_bar()
        self.refresh_table()

    def create_widgets(self):
        # -------- Budget Frame --------
        budget_frame = tk.Frame(self.root, bg="#ffffff", bd=2, relief="raised")
        budget_frame.pack(pady=10, padx=10, fill="x")
        self.budget_label = tk.Label(budget_frame, text="Budget: 0 | Spent: 0 | Savings: 0",
                                     font=("Consolas", 14, "bold"), bg="#ffffff")
        self.budget_label.pack(pady=10, padx=10)
        self.progress = ttk.Progressbar(budget_frame, length=400, maximum=100)
        self.progress.pack(pady=10)
        btns_row = tk.Frame(budget_frame, bg="#ffffff")
        btns_row.pack(pady=5)
        budget_btn = tk.Button(btns_row, text="Set Budget", font=("Consolas", 12, "bold"),
                               command=self.set_budget_dialog, bg="#007bff", fg="white")
        budget_btn.pack(side="left", padx=5)
        cat_limit_btn = tk.Button(btns_row, text="Set Category Limit", font=("Consolas", 12, "bold"),
                                  command=self.set_category_limit_dialog, bg="#6f42c1", fg="white")
        cat_limit_btn.pack(side="left", padx=5)
        mark_unwanted_btn = tk.Button(btns_row, text="Mark Unwanted", font=("Consolas", 12, "bold"),
                                      command=self.mark_unwanted_dialog, bg="#fd7e14", fg="white")
        mark_unwanted_btn.pack(side="left", padx=5)
        suggest_btn = tk.Button(btns_row, text="Get Suggestions", font=("Consolas", 12, "bold"),
                                command=self.show_suggestions, bg="#20c997", fg="white")
        suggest_btn.pack(side="left", padx=5)
        # block mode toggle
        self.block_var = tk.BooleanVar(value=get_block_mode())
        block_check = tk.Checkbutton(btns_row, text="Block Unwanted (ON/OFF)", var=self.block_var,
                                     command=self.toggle_block_mode, bg="#ffffff", font=("Consolas",10,"bold"))
        block_check.pack(side="left", padx=5)

        # -------- Add Expense Frame --------
        add_frame = tk.Frame(self.root, bg="#ffffff", bd=2, relief="raised")
        add_frame.pack(pady=10, padx=10, fill="x")
        tk.Label(add_frame, text="Amount:", font=("Consolas",12), bg="#ffffff").grid(row=0, column=0, padx=5, pady=5)
        self.amount_entry = tk.Entry(add_frame, font=("Consolas",12), width=25)
        self.amount_entry.grid(row=0, column=1, padx=5, pady=5)
        tk.Label(add_frame, text="Category:", font=("Consolas",12), bg="#ffffff").grid(row=1, column=0, padx=5, pady=5)
        self.category_var = tk.StringVar(value=CATEGORIES[0])
        self.category_menu = tk.OptionMenu(add_frame, self.category_var, *CATEGORIES)
        self.category_menu.config(font=("Consolas",12))
        self.category_menu.grid(row=1, column=1, padx=5, pady=5)
        tk.Label(add_frame, text="Description:", font=("Consolas",12), bg="#ffffff").grid(row=2, column=0, padx=5, pady=5)
        self.desc_entry = tk.Entry(add_frame, font=("Consolas",12), width=25)
        self.desc_entry.grid(row=2, column=1, padx=5, pady=5)
        tk.Label(add_frame, text="Date (YYYY-MM-DD):", font=("Consolas",12), bg="#ffffff").grid(row=3, column=0, padx=5, pady=5)
        self.date_entry = tk.Entry(add_frame, font=("Consolas",12), width=25)
        self.date_entry.insert(0, datetime.date.today().strftime("%Y-%m-%d"))
        self.date_entry.grid(row=3, column=1, padx=5, pady=5)
        tk.Button(add_frame, text="Add Expense", font=("Consolas",12,"bold"),
                  command=self.add_expense_action, bg="#28a745", fg="white").grid(row=4, column=0, columnspan=2, pady=10)

        # -------- Expense Table Frame --------
        table_frame = tk.Frame(self.root, bg="#f0f2f5")
        table_frame.pack(padx=10, pady=10, fill="both", expand=True)
        self.tree = ttk.Treeview(table_frame, columns=("ID","Amount","Category","Description","Date"), show="headings", height=10)
        for col in ("ID","Amount","Category","Description","Date"):
            self.tree.heading(col, text=col)
        style = ttk.Style()
        style.configure("Treeview", font=("Consolas",12), rowheight=25)
        style.configure("Treeview.Heading", font=("Consolas",12,"bold"))
        self.tree.pack(expand=True, fill="both", pady=5)

        # Buttons below the table
        btn_frame = tk.Frame(table_frame, bg="#f0f2f5")
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Delete Selected", font=("Consolas",12,"bold"),
                  command=self.delete_selected, bg="#dc3545", fg="white").pack(side="left", padx=5)
        tk.Button(btn_frame, text="Refresh", font=("Consolas",12,"bold"),
                  command=lambda: [self.refresh_table(), self.refresh_budget_bar()],
                  bg="#17a2b8", fg="white").pack(side="left", padx=5)

        # -------- Reports & Export Frame --------
        report_frame = tk.Frame(self.root, bg="#f0f2f5")
        report_frame.pack(pady=10)
        tk.Button(report_frame, text="Category Pie", font=("Consolas",12,"bold"),
                  command=show_category_pie, bg="#17a2b8", fg="white").pack(side="left", padx=5)
        tk.Button(report_frame, text="Monthly Trend", font=("Consolas",12,"bold"),
                  command=show_monthly_trend, bg="#17a2b8", fg="white").pack(side="left", padx=5)
        tk.Button(report_frame, text="Export Excel", font=("Consolas",12,"bold"),
                  command=self.export_excel, bg="#ffc107", fg="white").pack(side="left", padx=5)
        tk.Button(report_frame, text="Export PDF", font=("Consolas",12,"bold"),
                  command=self.export_pdf, bg="#ffc107", fg="white").pack(side="left", padx=5)

    # ---- Actions ----
    def add_expense_action(self):
        try:
            amount = float(self.amount_entry.get())
            if amount <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Invalid amount.")
            return
        date = self.date_entry.get()
        try:
            datetime.datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Error", "Date must be YYYY-MM-DD.")
            return
        category = self.category_var.get()
        desc = self.desc_entry.get()

        # Check before adding (category limits, unwanted + block mode, budget)
        if not self.check_before_add_expense(amount, category, date):
            return

        add_expense(amount, category, desc, date)
        self.amount_entry.delete(0, tk.END)
        self.desc_entry.delete(0, tk.END)
        self.refresh_budget_bar()
        self.refresh_table()

    def check_before_add_expense(self, amount, category, date):
        # returns True to proceed, False to cancel
        try:
            y, m, _ = map(int, date.split("-"))
        except Exception:
            messagebox.showerror("Error", "Invalid date format.")
            return False

        # 1) per-category limit check
        cat_limit = get_category_limit(category)
        cat_spent = get_month_spent_by_category(y, m, category)
        if cat_limit is not None and (cat_spent + amount) > cat_limit:
            # show clear warning and choice
            resp = messagebox.askyesno("Category limit exceeded",
                                       f"Adding ₹{amount:.2f} will exceed the limit for '{category}' (limit ₹{cat_limit:.2f}).\nDo you want to CANCEL this expense?")
            if resp:
                return False  # user chose to cancel
            # else allow to continue

        # 2) unwanted category & block mode
        if is_category_unwanted(category) and get_block_mode():
            messagebox.showwarning("Blocked", f"'{category}' is marked as UNWANTED and block mode is ON. You cannot add this expense.")
            return False

        # 3) monthly budget check (soft warning)
        budget = get_budget()
        spent = get_total_expenses_for_month(y, m)
        new_spent = spent + amount
        if budget > 0 and new_spent > budget:
            resp = messagebox.askyesno("Budget exceeded",
                f"This expense will make monthly spend exceed budget (Budget ₹{budget:.2f}).\nSpent now: ₹{spent:.2f}.\nAdd anyway?")
            if not resp:
                return False

        return True

    def refresh_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        expenses = fetch_expenses()
        for exp in expenses:
            self.tree.insert("", "end", values=exp)

    def delete_selected(self):
        for item in self.tree.selection():
            expense_id = self.tree.item(item)["values"][0]
            delete_expense(expense_id)
        self.refresh_table()
        self.refresh_budget_bar()

    def refresh_budget_bar(self):
        budget = get_budget()
        today = datetime.date.today()
        spent = get_total_expenses_for_month(today.year, today.month)
        savings = budget - spent
        if savings < 0:
            savings = 0
        self.budget_label.config(text=f"Budget: {budget:.0f} | Spent: {spent:.0f} | Savings: {savings:.0f}")
        percent = (spent / budget) * 100 if budget > 0 else 0
        if percent < 0: percent = 0
        if percent > 100: percent = 100
        self.progress["value"] = percent

    def set_budget_dialog(self):
        def save_budget():
            try:
                amount = float(entry.get())
                set_budget(amount)
                self.refresh_budget_bar()
                win.destroy()
            except ValueError:
                messagebox.showerror("Error", "Invalid budget amount.")
        win = tk.Toplevel(self.root)
        win.title("Set Budget")
        win.configure(bg="#f0f2f5")
        tk.Label(win, text="Enter Monthly Budget:", font=("Consolas",14,"bold"), bg="#f0f2f5").pack(padx=10, pady=10)
        entry = tk.Entry(win, font=("Consolas",14), width=20)
        entry.pack(padx=10, pady=5)
        tk.Button(win, text="Save", font=("Consolas",12,"bold"), bg="#28a745", fg="white", command=save_budget).pack(pady=10)

    def set_category_limit_dialog(self):
        def save_limit():
            try:
                amt = float(entry.get())
                set_category_limit(catvar.get(), amt)
                messagebox.showinfo("Saved", f"Limit for {catvar.get()} set to ₹{amt:.2f}")
                win.destroy()
            except ValueError:
                messagebox.showerror("Error", "Invalid amount.")
        win = tk.Toplevel(self.root); win.title("Set Category Limit")
        tk.Label(win, text="Category:", font=("Consolas",12)).grid(row=0,column=0,padx=5,pady=5)
        catvar = tk.StringVar(value=CATEGORIES[0])
        tk.OptionMenu(win, catvar, *CATEGORIES).grid(row=0,column=1,padx=5,pady=5)
        tk.Label(win, text="Limit (₹):", font=("Consolas",12)).grid(row=1,column=0,padx=5,pady=5)
        entry = tk.Entry(win); entry.grid(row=1,column=1,padx=5,pady=5)
        tk.Button(win, text="Save", command=save_limit, bg="#28a745", fg="white").grid(row=2,column=0,columnspan=2,pady=10)

    def mark_unwanted_dialog(self):
        def save_unwanted():
            cat = catvar.get()
            unw = var.get()
            mark_category_unwanted(cat, unw)
            messagebox.showinfo("Saved", f"Category '{cat}' unwanted set to {unw}.")
            win.destroy()
        win = tk.Toplevel(self.root); win.title("Mark Unwanted Category")
        tk.Label(win, text="Category:", font=("Consolas",12)).grid(row=0,column=0,padx=5,pady=5)
        catvar = tk.StringVar(value=CATEGORIES[0])
        tk.OptionMenu(win, catvar, *CATEGORIES).grid(row=0,column=1,padx=5,pady=5)
        var = tk.BooleanVar(value=False)
        tk.Checkbutton(win, text="Mark as Unwanted (blockable)", var=var).grid(row=1,column=0,columnspan=2,padx=5,pady=5)
        tk.Button(win, text="Save", command=save_unwanted, bg="#fd7e14").grid(row=2,column=0,columnspan=2,pady=10)

    def toggle_block_mode(self):
        enabled = self.block_var.get()
        set_block_mode(enabled)
        messagebox.showinfo("Block Mode", f"Block unwanted mode set to {enabled}.")

    def show_suggestions(self):
        today = datetime.date.today()
        suggestions = recommend_actions_for_month(today.year, today.month)
        text = "\n".join(suggestions)
        # show in scrollable window
        win = tk.Toplevel(self.root); win.title("Suggestions")
        txt = tk.Text(win, wrap="word", width=60, height=15, font=("Consolas",11))
        txt.pack(padx=10, pady=10)
        txt.insert("1.0", text)
        txt.config(state="disabled")
        tk.Button(win, text="Close", command=win.destroy, bg="#6c757d", fg="white").pack(pady=5)

    def export_excel(self):
        expenses = fetch_expenses()
        if not expenses:
            messagebox.showinfo("No Data", "No expenses to export.")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                                filetypes=[("Excel Files", "*.xlsx")])
        if filename:
            export_to_excel(expenses, filename)
            messagebox.showinfo("Success", "Exported to Excel.")

    def export_pdf(self):
        expenses = fetch_expenses()
        if not expenses:
            messagebox.showinfo("No Data", "No expenses to export.")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".pdf",
                                                filetypes=[("PDF Files", "*.pdf")])
        if filename:
            export_to_pdf(expenses, filename)
            messagebox.showinfo("Success", "Exported to PDF.")

# ---------------- Main ----------------
if __name__ == "__main__":
    init_db()
    root = tk.Tk()
    app = ExpenseTrackerApp(root)
    root.mainloop()

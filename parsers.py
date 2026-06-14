# parsers.py

import re
from datetime import datetime
from pathlib import Path

def parse_tasks_and_expenses(note_text):
    """
    Extract tasks and expenses from a single note. Supports multiple formats,
    natural language expressions, and Markdown structural context.
    """
    lines = note_text.split('\n')
    task_data = []
    expense_data = []
    
    # ----------------------------------------------------
    # Task Parsing Regex Patterns
    # ----------------------------------------------------
    # 1. Standard checkbox formats: - [ ], - [x], * [ ], * [x], [ ], [x], - [], []
    checkbox_pattern = re.compile(r"^\s*[-*]?\s*\[\s*([ xX]?)\s*\]\s*(.+)$")
    checkbox_empty_pattern = re.compile(r"^\s*[-*]?\s*\[\]\s*(.+)$")
    
    # 2. Prefixed tasks: todo: buy milk, task: code, action: test
    prefix_task_pattern = re.compile(r"^\s*[-*]?\s*(?:todo|task|action|to-do)\s*:\s*(.+)$", re.IGNORECASE)
    
    # ----------------------------------------------------
    # Expense Parsing Regex Patterns
    # ----------------------------------------------------
    # Currency symbols/codes
    currency_regex = r"(?:[$₹€£]|Rs\.?|INR|USD|EUR|GBP)"
    
    # 1. Spent/Paid pattern: Spent 500 on coffee, paid 1200 for petrol
    spent_pattern = re.compile(
        r"^\s*[-*]?\s*(?:spent|paid)\s+(?:" + currency_regex + r"\s*)?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:" + currency_regex + r"\s*)?(?:on|for)\s+(.+)$", 
        re.IGNORECASE
    )
    
    # 2. Bought pattern: Bought a book for 350, Bought grocery for Rs 200
    bought_pattern = re.compile(
        r"^\s*[-*]?\s*bought\s+(?:a\s+|an\s+)?(.+?)\s+for\s+(?:" + currency_regex + r"\s*)?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:" + currency_regex + r"\s*)?$",
        re.IGNORECASE
    )
    
    # 3. Cost pattern: coffee cost 120, book cost me $15
    cost_pattern = re.compile(
        r"^\s*[-*]?\s*(.+?)\s+cost\s+(?:me\s+)?(?:" + currency_regex + r"\s*)?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:" + currency_regex + r"\s*)?$",
        re.IGNORECASE
    )
    
    # 4. Bullet with separator: - Dinner - 250, - Lunch: Rs. 150
    bullet_kv_pattern = re.compile(
        r"^\s*[-*]\s*(.+?)\s*[-–—:]\s*(?:" + currency_regex + r"\s*)?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:" + currency_regex + r"\s*)?$",
        re.IGNORECASE
    )

    # 5. Bullet with space and currency (no separator): - Dinner ₹250
    bullet_space_price_pattern = re.compile(
        r"^\s*[-*]\s*(.+?)\s+(?:" + currency_regex + r"\s*)(\d+(?:,\d{3})*(?:\.\d+)?)\s*$",
        re.IGNORECASE
    )
    
    # Keep track of markdown section context
    inside_tasks_section = False
    inside_expenses_section = False
    
    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            continue
            
        # Check for headers to update section context
        header_match = re.match(r"^(#+)\s*(.+)$", line_strip)
        if header_match:
            header_title = header_match.group(2).strip().lower()
            if any(k in header_title for k in ["task", "todo", "to-do", "to do", "action item"]):
                inside_tasks_section = True
                inside_expenses_section = False
            elif any(k in header_title for k in ["expense", "budget", "cost", "spending", "price", "pricing"]):
                inside_expenses_section = True
                inside_tasks_section = False
            else:
                inside_tasks_section = False
                inside_expenses_section = False
            continue
            
        # 1. PARSE TASKS
        is_task = False
        task_desc = None
        task_status = "todo"
        
        # A. Checkbox match
        cb_match = checkbox_pattern.match(line)
        if cb_match:
            status_char = cb_match.group(1)
            task_desc = cb_match.group(2).strip()
            task_status = "done" if status_char.lower() == "x" else "todo"
            is_task = True
        else:
            cb_empty_match = checkbox_empty_pattern.match(line)
            if cb_empty_match:
                task_desc = cb_empty_match.group(1).strip()
                task_status = "todo"
                is_task = True
                
        # B. Prefix match (todo: ...)
        if not is_task:
            prefix_match = prefix_task_pattern.match(line)
            if prefix_match:
                task_desc = prefix_match.group(1).strip()
                task_status = "todo"
                is_task = True
                
        # C. Simple bullet under Tasks/Todo section
        if not is_task and inside_tasks_section:
            bullet_match = re.match(r"^\s*[-*]\s*(.+)$", line)
            if bullet_match:
                task_desc = bullet_match.group(1).strip()
                task_status = "todo"
                is_task = True
                
        if is_task and task_desc:
            # Avoid duplicate or mis-parsed headers or checklist markers
            task_desc = re.sub(r"^\s*[-*]\s*", "", task_desc)
            task_data.append({
                "task": task_desc,
                "status": task_status
            })
            continue
            
        # 2. PARSE EXPENSES
        is_expense = False
        exp_cat = None
        exp_amount = None
        
        # A. Spent/Paid match (e.g. Spent 500 on coffee)
        match_spent = spent_pattern.match(line)
        if match_spent:
            exp_amount = match_spent.group(1)
            exp_cat = match_spent.group(2).strip()
            is_expense = True
            
        # B. Bought match (e.g. Bought a book for 350)
        if not is_expense:
            match_bought = bought_pattern.match(line)
            if match_bought:
                exp_cat = match_bought.group(1).strip()
                exp_amount = match_bought.group(2)
                is_expense = True
                
        # C. Cost match (e.g. Coffee cost me 120)
        if not is_expense:
            match_cost = cost_pattern.match(line)
            if match_cost:
                exp_cat = match_cost.group(1).strip()
                exp_amount = match_cost.group(2)
                is_expense = True
                
        # D. Bullet point with category and price (separated)
        if not is_expense:
            match_bullet = bullet_kv_pattern.match(line)
            if match_bullet:
                exp_cat = match_bullet.group(1).strip()
                exp_amount = match_bullet.group(2)
                # Ignore metadata-like lines
                if exp_cat.lower() not in {"version", "last updated", "updated", "date", "id", "year", "stage", "status"}:
                    is_expense = True
                    
        # E. Bullet point with category and price (space and currency)
        if not is_expense:
            match_bullet_space = bullet_space_price_pattern.match(line)
            if match_bullet_space:
                exp_cat = match_bullet_space.group(1).strip()
                exp_amount = match_bullet_space.group(2)
                is_expense = True

        # F. Simple bullet under Expenses/Budget section
        if not is_expense and inside_expenses_section:
            # Match any bullet line containing a name and a number
            match_section_bullet = re.match(r"^\s*[-*]\s*(.+?)\s*[-–—:]?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*$", line)
            if match_section_bullet:
                exp_cat = match_section_bullet.group(1).strip()
                exp_amount = match_section_bullet.group(2)
                is_expense = True
                
        if is_expense and exp_cat and exp_amount:
            # Clean up the category
            exp_cat = re.sub(r"^\s*[-*]\s*", "", exp_cat)
            if exp_cat.lower().startswith("expense:"):
                exp_cat = exp_cat[8:].strip()
            exp_cat = re.sub(r"\s*[-–—:]\s*$", "", exp_cat).strip()
            
            try:
                val = float(exp_amount.replace(",", ""))
                expense_data.append({
                    "category": exp_cat,
                    "amount": val
                })
            except ValueError:
                pass
            continue
            
    return task_data, expense_data

def aggregate_notes(folder_path="notes", user_id=None):
    """
    Load all .md and .txt notes, parse and return structured tasks and expenses.
    If user_id is provided, loads notes from DatabaseFile model.
    """
    all_tasks, all_expenses = [], []
    if user_id:
        from api.models import DatabaseFile
        prefix = f"user_{user_id}/"
        db_files = DatabaseFile.objects.filter(name__startswith=prefix)
        for db_file in db_files:
            if db_file.name.endswith(('.md', '.txt')):
                try:
                    content = db_file.content.decode('utf-8')
                except Exception:
                    continue
                tasks, expenses = parse_tasks_and_expenses(content)
                filename = db_file.name.split('/')[-1]
                stem = filename.split('.')[0]
                date_str = stem if stem[:4].isdigit() else None
                for task in tasks:
                    task["date"] = date_str
                for expense in expenses:
                    expense["date"] = date_str
                all_tasks.extend(tasks)
                all_expenses.extend(expenses)
        return all_tasks, all_expenses

    for ext in ["**/*.md", "**/*.txt"]:
        for file in Path(folder_path).glob(ext):
            with open(file, "r", encoding="utf-8") as f:
                content = f.read()
            tasks, expenses = parse_tasks_and_expenses(content)
            date_str = file.stem if file.stem[:4].isdigit() else None
            for task in tasks:
                task["date"] = date_str
            for expense in expenses:
                expense["date"] = date_str
            all_tasks.extend(tasks)
            all_expenses.extend(expenses)
    return all_tasks, all_expenses

# parsers.py

import re
from datetime import datetime
from pathlib import Path

_aggregate_notes_cache = {}


def invalidate_aggregate_notes_cache(user_id):
    _aggregate_notes_cache.pop(user_id, None)


def parse_tasks_and_expenses(note_text):
    """
    Extract tasks and expenses from a single note. Supports multiple formats,
    natural language expressions, and Markdown structural context.
    """
    note_text = note_text.lstrip('\ufeff')
    if note_text.startswith('\ufeff'):
        note_text = note_text[1:]
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
    task_label_pattern = re.compile(r"^\s*(?:task|todo|to-do|action)\s*:\s*(.+)$", re.IGNORECASE)
    finance_label_pattern = re.compile(r"\b(?:finance|expense|budget|cost)\s*:\s*(.+)$", re.IGNORECASE)
    
    # ----------------------------------------------------
    # Expense Parsing Regex Patterns
    # ----------------------------------------------------
    # Currency symbols/codes
    currency_regex = r"(?:[$₹€£]|Rs\.?|INR|USD|EUR|GBP)"
    
    # 1. Spent/Paid pattern: Spent 500 on coffee, paid 1200 for petrol
    spent_pattern = re.compile(
        r"^\s*[-*]?\s*(?:\b(?:i|we|they|you)\b\s+)?(?:spent|paid)\s+(?:" + currency_regex + r"\s*)?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:" + currency_regex + r"\s*)?(?:on|for)\s+(.+?)(?:\s+and\s+|$)",
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

    # 5.5 Bullet with price first, then category (e.g. - ₹250 - Food)
    bullet_amount_first_pattern = re.compile(
        r"^\s*[-*]\s*(?:" + currency_regex + r"\s*)?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:" + currency_regex + r"\s*)?\s*[-–—:]\s*(.+)$",
        re.IGNORECASE
    )

    # 6. Narrative finance phrase: paid $120 for office supplies
    narrative_expense_pattern = re.compile(
        r"\b(?:\b(?:i|we|they|you)\b\s+)?(?:paid|spent|bought)\s+(?:" + currency_regex + r"\s*)?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:" + currency_regex + r"\s*)?(?:on|for)\s+(.+?)(?:\s+and\s+|$)",
        re.IGNORECASE
    )
    
    # Keep track of markdown section context
    inside_tasks_section = False
    inside_expenses_section = False
    
    for line in lines:
        line_strip = line.lstrip('\ufeff').strip()
        if not line_strip:
            continue
            
        # Check for headers to update section context
        header_match = re.match(r"^(#+)\s*(.+)$", line_strip)
        if header_match:
            header_title = header_match.group(2).strip().lower()
            if any(k in header_title for k in ["task", "todo", "to-do", "to do", "action item"]):
                inside_tasks_section = True
                inside_expenses_section = False
            elif any(k in header_title for k in ["expense", "budget", "cost", "spending", "price", "pricing", "finance", "finances", "financial"]):
                inside_expenses_section = True
                inside_tasks_section = False
            else:
                inside_tasks_section = False
                inside_expenses_section = False
            continue
            
        task_handled_by_label = False
        line_for_task = line_strip
        line_for_expense = line_strip

        task_label_match = task_label_pattern.match(line_strip)
        finance_label_match = finance_label_pattern.search(line_strip)
        if task_label_match:
            task_desc = task_label_match.group(1).strip()
            task_desc = re.split(r"\b(?:finance|expense|budget|cost)\b\s*:", task_desc, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            if task_desc:
                task_data.append({
                    "task": task_desc,
                    "status": "todo"
                })
            task_handled_by_label = True

        if finance_label_match:
            line_for_expense = finance_label_match.group(1).strip()

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
        if not is_task and not task_handled_by_label:
            prefix_match = prefix_task_pattern.match(line)
            if prefix_match:
                task_desc = prefix_match.group(1).strip()
                task_status = "todo"
                is_task = True
                
        # C. Simple bullet under Tasks/Todo section
        if not is_task and not task_handled_by_label and inside_tasks_section:
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

        finance_label_match = finance_label_pattern.search(line_strip)
        if finance_label_match:
            line_for_expense = finance_label_match.group(1).strip()
        else:
            line_for_expense = line_strip
        
        # A. Spent/Paid match (e.g. Spent 500 on coffee)
        match_spent = spent_pattern.match(line_for_expense)
        if match_spent:
            exp_amount = match_spent.group(1)
            exp_cat = match_spent.group(2).strip()
            is_expense = True
            
        # B. Bought match (e.g. Bought a book for 350)
        if not is_expense:
            match_bought = bought_pattern.match(line_for_expense)
            if match_bought:
                exp_cat = match_bought.group(1).strip()
                exp_amount = match_bought.group(2)
                is_expense = True
                
        # C. Cost match (e.g. Coffee cost me 120)
        if not is_expense:
            match_cost = cost_pattern.match(line_for_expense)
            if match_cost:
                exp_cat = match_cost.group(1).strip()
                exp_amount = match_cost.group(2)
                is_expense = True
                
        # D. Bullet point with category and price (separated)
        if not is_expense:
            match_bullet = bullet_kv_pattern.match(line_for_expense)
            if match_bullet:
                exp_cat = match_bullet.group(1).strip()
                exp_amount = match_bullet.group(2)
                # Ignore metadata-like lines
                if exp_cat.lower() not in {"version", "last updated", "updated", "date", "id", "year", "stage", "status"}:
                    is_expense = True
                    
        # E. Bullet point with category and price (space and currency)
        if not is_expense:
            match_bullet_space = bullet_space_price_pattern.match(line_for_expense)
            if match_bullet_space:
                exp_cat = match_bullet_space.group(1).strip()
                exp_amount = match_bullet_space.group(2)
                is_expense = True

        # E2. Bullet point with price first, then category (e.g. - ₹250 - Food)
        if not is_expense:
            match_amount_first = bullet_amount_first_pattern.match(line_for_expense)
            if match_amount_first:
                exp_amount = match_amount_first.group(1)
                exp_cat = match_amount_first.group(2).strip()
                is_expense = True

        # F. Narrative finance phrase (e.g. paid $120 for office supplies)
        if not is_expense:
            match_narrative = narrative_expense_pattern.search(line_for_expense)
            if match_narrative:
                exp_amount = match_narrative.group(1)
                exp_cat = match_narrative.group(2).strip()
                exp_cat = re.sub(r"\s+(?:and|received|spent|paid|bought|today|from|client|payment).*$", "", exp_cat, flags=re.IGNORECASE).strip()
                exp_cat = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", exp_cat).strip()
                is_expense = True

        # G. Simple bullet under Expenses/Budget section
        if not is_expense and inside_expenses_section:
            # Match any bullet line containing a name and a number
            match_section_bullet = re.match(r"^\s*[-*]\s*(.+?)\s*[-–—:]?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*$", line_for_expense)
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
        note_files = [db_file for db_file in db_files if db_file.name.endswith(('.md', '.txt'))]
        for db_file in note_files:
            try:
                content = bytes(db_file.content).decode('utf-8')
            except (UnicodeDecodeError, AttributeError, TypeError) as e:
                print(f"Error decoding file {db_file.name}: {e}")
                continue
            tasks, expenses = parse_tasks_and_expenses(content)
            filename = db_file.name.split('/')[-1]
            stem = filename.split('.')[0]
            date_str = stem if (stem and stem[:4].isdigit()) else db_file.updated_at.strftime('%Y-%m-%d')
            for task in tasks:
                task["date"] = date_str
            for expense in expenses:
                expense["date"] = date_str
            all_tasks.extend(tasks)
            all_expenses.extend(expenses)

        if not note_files:
            for ext in ["**/*.md", "**/*.txt"]:
                for file in Path(folder_path).glob(ext):
                    with open(file, "r", encoding="utf-8") as f:
                        content = f.read()
                    tasks, expenses = parse_tasks_and_expenses(content)
                    date_str = file.stem if (file.stem and file.stem[:4].isdigit()) else datetime.fromtimestamp(file.stat().st_mtime).strftime('%Y-%m-%d')
                    for task in tasks:
                        task["date"] = date_str
                    for expense in expenses:
                        expense["date"] = date_str
                    all_tasks.extend(tasks)
                    all_expenses.extend(expenses)

        _aggregate_notes_cache[user_id] = (all_tasks, all_expenses)
        return all_tasks, all_expenses

    for ext in ["**/*.md", "**/*.txt"]:
        for file in Path(folder_path).glob(ext):
            with open(file, "r", encoding="utf-8") as f:
                content = f.read()
            tasks, expenses = parse_tasks_and_expenses(content)
            date_str = file.stem if (file.stem and file.stem[:4].isdigit()) else datetime.fromtimestamp(file.stat().st_mtime).strftime('%Y-%m-%d')
            for task in tasks:
                task["date"] = date_str
            for expense in expenses:
                expense["date"] = date_str
            all_tasks.extend(tasks)
            all_expenses.extend(expenses)
    return all_tasks, all_expenses


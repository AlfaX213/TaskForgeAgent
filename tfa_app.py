import sqlite3
import os
import json
from unittest import result
from openai import OpenAI  # type: ignore
import webbrowser
from pathlib import Path
import base64
from datetime import datetime, date, time 
import streamlit as st  # type: ignore
from streamlit_autorefresh import st_autorefresh  # type: ignore


# =========================
# AI CONFIG
# =========================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "openrouter/free"

# =========================
# CONFIG
# =========================
APP_VERSION = "1.0.0"

# Path to the local SQLite database file
DB_PATH = "productivity_agent.db"

# Add changelog content (if exists) for display in the UI
def load_changelog() -> str:
    try:
        with open("CHANGELOG.md", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "No changelog found."

# Predefined websites for quick actions
QUICK_ACTIONS = {
    "linkedin": "https://www.linkedin.com",
    "gmail": "https://mail.google.com",
    "jobstreet": "https://www.jobstreet.co.id",
    "notion": "https://www.notion.so",
    "drive": "https://drive.google.com",
    "docs": "https://docs.google.com",
    "calendar": "https://calendar.google.com",
    "youtube": "https://www.youtube.com",
}

# Predefined local folders for quick access
LOCAL_FOLDERS = {
    "cv folder": str(Path.home() / "Documents"),
    "notes folder": str(Path.home() / "Documents"),
}


# Create and return a database connection
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# Initialize database connection
conn = get_conn()


# Create tables if they do not exist yet
def init_db() -> None:
    with conn:
        # Table for tasks
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                is_done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

        # Add new task columns if database was created before these features existed
        task_columns = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
        ]

        if "priority" not in task_columns:
            conn.execute(
                "ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'"
            )

        if "due_date" not in task_columns:
            conn.execute(
                "ALTER TABLE tasks ADD COLUMN due_date TEXT"
            )

        if "category" not in task_columns:
            conn.execute(
                "ALTER TABLE tasks ADD COLUMN category TEXT"
            )

        # Table for reminders
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                remind_at TEXT,
                is_triggered INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

        # Table for notes
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # Table for goals
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'in_progress',
                target_date TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        # Add is_triggered column if database was created before this feature existed
        reminder_columns = [
            row["name"]
            for row in conn.execute("PRAGMA table_info(reminders)").fetchall()
        ]
        if "is_triggered" not in reminder_columns:
            conn.execute(
                "ALTER TABLE reminders ADD COLUMN is_triggered INTEGER NOT NULL DEFAULT 0"
            )
# Run database initialization
init_db()


# Get current datetime as string
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# -----------------------------
# Database helpers
# -----------------------------


# Create OpenRouter Client function
def ask_openrouter(user_input: str) -> dict:
    if not OPENROUTER_API_KEY:
        return {
            "intent": "error",
            "message": "OPENROUTER_API_KEY is not set."
        }

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )

    system_prompt = """
You are the decision layer for a local productivity agent.

Your job is to classify the user's request and return ONLY valid JSON.

AAvailable intents:
- add_task
- show_tasks
- complete_task
- add_reminder
- show_reminders
- delete_reminder
- save_note
- show_notes
- open_quick_action
- summarize_text
- add_goal
- show_goals
- complete_goal
- pause_goal
- resume_goal
- delete_goal
- general_reply
Return JSON in this format:
{
  "intent": "...",
  "content": "...",
  "task_id": null,
  "goal_id": null,
  "remind_at": null,
  "target": null,
  "text": null,
  "status": null,
  "message": "..."
  "reminder_id": null,
}
Rules:
- For add_task, put task text in "content"
- For add_goal, put goal title in "content"
- For complete_goal, put integer in "goal_id"
- For pause_goal, put integer in "goal_id"
- For resume_goal, put integer in "goal_id"
- For delete_goal, put integer in "goal_id"
- For show_goals, no extra field is needed
- For complete_task, put integer in "task_id"
- For add_reminder, put reminder text in "content" and optional datetime in "remind_at"
- For delete_reminder, put integer in "reminder_id"
- For save_note, put note text in "content"
- For open_quick_action, put target in "target"
- For summarize_text, put source text in "text"
- For general_reply, use "message"
- If unsure, use general_reply
- Output JSON only, no markdown
"""

    response = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
    )

    raw = response.choices[0].message.content
    return json.loads(raw)
# Create the Agent Router
def agent_router(user_input: str) -> str:
    try:
        result = ask_openrouter(user_input)
    except Exception as e:
        return f"AI routing error: {e}"

    intent = result.get("intent")

    if intent == "add_task":
        return add_task(result.get("content", ""))

    if intent == "show_tasks":
        tasks = list_tasks()
        return "Tasks loaded below." if tasks else "No tasks found."

    if intent == "complete_task":
        task_id = result.get("task_id")
        if isinstance(task_id, int):
            return complete_task(task_id)
        return "Could not determine which task to complete."

    if intent == "add_reminder":
        return add_reminder(
            result.get("content", ""),
            result.get("remind_at"),
        )
    if intent == "delete_reminder":
        reminder_id = result.get("reminder_id")
        if isinstance(reminder_id, int):
            return delete_reminders([reminder_id])
        return "Could not determine which reminder to delete."
    
    if intent == "add_goal":
        return add_goal(result.get("content", ""))

    if intent == "show_goals":
        goals = list_goals()
        return "Goals loaded below." if goals else "No goals found."

    if intent == "complete_goal":
        goal_id = result.get("goal_id")
        if isinstance(goal_id, int):
            return update_goal_status(goal_id, "completed")
        return "Could not determine which goal to complete."

    if intent == "pause_goal":
        goal_id = result.get("goal_id")
        if isinstance(goal_id, int):
            return update_goal_status(goal_id, "paused")
        return "Could not determine which goal to pause."

    if intent == "resume_goal":
        goal_id = result.get("goal_id")
        if isinstance(goal_id, int):
            return update_goal_status(goal_id, "in_progress")
        return "Could not determine which goal to resume."

    if intent == "show_reminders":
        reminders = list_reminders()
        return "Reminders loaded below." if reminders else "No reminders found."

    if intent == "save_note":
        return add_note(result.get("content", ""))

    if intent == "show_notes":
        notes = list_notes()
        return "Notes loaded below." if notes else "No notes found."

    if intent == "open_quick_action":
        return run_quick_action(result.get("target", ""))

    if intent == "summarize_text":
        return simple_summary(result.get("text", ""))

    if intent == "general_reply":
        return result.get("message", "I understood the message, but no action was needed.")

    if intent == "error":
        return result.get("message", "AI configuration error.")

    return "The AI could not determine a valid action."
# Add a new task into the database
def add_task(content: str) -> str:
    content = content.strip()
    if not content:
        return "Task cannot be empty."
    with conn:
        conn.execute(
            "INSERT INTO tasks (content, created_at) VALUES (?, ?)",
            (content, now_str()),
        )
    return f"Task added: {content}"


# Retrieve all tasks from database
def list_tasks() -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT id, content, is_done, priority, due_date, category, created_at
        FROM tasks
        ORDER BY is_done ASC, id DESC
        """
    )
    return cur.fetchall()


# Mark a task as completed
def complete_task(task_id: int) -> str:
    with conn:
        cur = conn.execute("UPDATE tasks SET is_done = 1 WHERE id = ?", (task_id,))
    if cur.rowcount == 0:
        return f"Task {task_id} was not found."
    return f"Task {task_id} marked as done."

#Delete task
def delete_tasks(task_ids: list[int]) -> str:
    if not task_ids:
        return "No tasks selected."

    placeholders = ",".join("?" for _ in task_ids)

    with conn:
        cur = conn.execute(
            f"DELETE FROM tasks WHERE id IN ({placeholders})",
            task_ids,
        )

    if cur.rowcount == 0:
        return "No matching tasks were found."

    if cur.rowcount == 1:
        return "1 task deleted."

    return f"{cur.rowcount} tasks deleted."
# Add a reminder with optional time
def add_reminder(content: str, remind_at: str | None = None) -> str:
    content = content.strip()
    if not content:
        return "Reminder content cannot be empty."

    clean_remind_at = remind_at.strip() if remind_at else None

    with conn:
        conn.execute(
            """
            INSERT INTO reminders (content, remind_at, is_triggered, created_at)
            VALUES (?, ?, 0, ?)
            """,
            (content, clean_remind_at, now_str()),
        )

    if clean_remind_at:
        return f"Reminder added: {content} at {clean_remind_at}"
    return f"Reminder added: {content}"


# Retrieve all reminders
def list_reminders() -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT id, content, remind_at, is_triggered, created_at
        FROM reminders
        ORDER BY id DESC
        """
    )
    return cur.fetchall()


# Save a short note
def add_note(content: str) -> str:
    content = content.strip()
    if not content:
        return "Note cannot be empty."
    with conn:
        conn.execute(
            "INSERT INTO notes (content, created_at) VALUES (?, ?)",
            (content, now_str()),
        )
    return "Note saved."


# Delete an existing note
def delete_note(note_id: int) -> str:
    with conn:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    if cur.rowcount == 0:
        return f"Note {note_id} was not found."
    return "Note deleted."


# Retrieve all notes
def list_notes() -> list[sqlite3.Row]:
    cur = conn.execute("SELECT id, content, created_at FROM notes ORDER BY id DESC")
    return cur.fetchall()

# Add a new goal
def add_goal(title: str, description: str = "", target_date: str | None = None) -> str:
    title = title.strip()
    description = description.strip()

    if not title:
        return "Goal title cannot be empty."

    with conn:
        conn.execute(
            """
            INSERT INTO goals (title, description, status, target_date, created_at)
            VALUES (?, ?, 'in_progress', ?, ?)
            """,
            (title, description, target_date, now_str()),
        )

    return f"Goal added: {title}"

# Mark a goal as completed
def complete_goal(goal_id: int) -> str:
    with conn:
        cur = conn.execute(
            "UPDATE goals SET status = 'completed' WHERE id = ?",
            (goal_id,),
        )
    if cur.rowcount == 0:
        return f"Goal {goal_id} was not found."
    return f"Goal {goal_id} marked as completed."


# Delete a goal
def delete_goal(goal_id: int) -> str:
    with conn:
        cur = conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    if cur.rowcount == 0:
        return f"Goal {goal_id} was not found."
    return "Goal deleted."

    # Retrieve all goals
def list_goals() -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT id, title, description, status, target_date, created_at
        FROM goals
        ORDER BY id DESC
        """
    )
    return cur.fetchall()

# Update goal status
def update_goal_status(goal_id: int, status: str) -> str:
    allowed_statuses = {"in_progress", "completed", "paused"}

    if status not in allowed_statuses:
        return "Invalid goal status."

    with conn:
        cur = conn.execute(
            "UPDATE goals SET status = ? WHERE id = ?",
            (status, goal_id),
        )

    if cur.rowcount == 0:
        return f"Goal {goal_id} was not found."

    return f"Goal {goal_id} updated to {status}."
# Update an existing note
def update_note(note_id: int, content: str) -> str:
    content = content.strip()
    if not content:
        return "Note cannot be empty."
    with conn:
        cur = conn.execute(
            "UPDATE notes SET content = ? WHERE id = ?",
            (content, note_id),
        )
    if cur.rowcount == 0:
        return f"Note {note_id} was not found."
    return "Note updated."


#play alarm sound from a local file (e.g. for reminders)
def play_alarm_from_file(file_path: str) -> None:
    try:
        with open(file_path, "rb") as f:
            st.audio(f.read(), format="audio/mp3", autoplay=True)
    except FileNotFoundError:
        st.warning("Alarm sound file not found.")

# Classify Tasks
def classify_task(task) -> str:
    if task["is_done"]:
        return "done"

    due_date = task["due_date"] if "due_date" in task.keys() else None

    if due_date:
        try:
            due = datetime.strptime(due_date, "%Y-%m-%d").date()
            today = datetime.now().date()

            if due < today:
                return "overdue"
            if due == today:
                return "today"
        except ValueError:
            pass

    return "pending"


def classify_reminder(reminder) -> str:
    if reminder["is_triggered"]:
        return "triggered"

    if reminder["remind_at"]:
        parsed = parse_reminder_datetime(reminder["remind_at"])
        if parsed:
            now = datetime.now()
            if parsed < now:
                return "overdue"
            return "upcoming"

    return "pending"
# -----------------------------
# Reminder helpers
# -----------------------------

def parse_reminder_datetime(value: str) -> datetime | None:
    value = value.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    return None


def get_due_reminders() -> list[sqlite3.Row]:
    now = datetime.now()
    reminders = conn.execute(
        """
        SELECT id, content, remind_at, is_triggered
        FROM reminders
        WHERE remind_at IS NOT NULL AND is_triggered = 0
        ORDER BY id ASC
        """
    ).fetchall()

    due = []
    for reminder in reminders:
        parsed_time = parse_reminder_datetime(reminder["remind_at"])
        if parsed_time and now >= parsed_time:
            due.append(reminder)

    return due


def mark_reminder_triggered(reminder_id: int) -> None:
    with conn:
        conn.execute(
            "UPDATE reminders SET is_triggered = 1 WHERE id = ?",
            (reminder_id,),
        )
def delete_reminders(reminder_ids: list[int]) -> str:
    if not reminder_ids:
        return "No reminders selected."

    placeholders = ",".join("?" for _ in reminder_ids)

    with conn:
        cur = conn.execute(
            f"DELETE FROM reminders WHERE id IN ({placeholders})",
            reminder_ids,
        )

    if cur.rowcount == 0:
        return "No matching reminders were found."

    if cur.rowcount == 1:
        return "1 reminder deleted."

    return f"{cur.rowcount} reminders deleted."


# -----------------------------
# Quick actions
# -----------------------------

# Execute predefined quick actions like opening websites or folders
def run_quick_action(target: str) -> str:
    key = target.strip().lower()

    if key in QUICK_ACTIONS:
        webbrowser.open(QUICK_ACTIONS[key])
        return f"Opened {key}."

    if key in LOCAL_FOLDERS:
        path = LOCAL_FOLDERS[key]
        webbrowser.open(Path(path).resolve().as_uri())
        return f"Opened {key}."

    return f"Quick action '{target}' is not supported yet."


# -----------------------------
# Command parser (for fallback)
# -----------------------------

# Interpret user command and route it to the correct function
def parse_command(command: str) -> str:
    raw = command.strip()
    lower = raw.lower()

    if not raw:
        return "Please enter a command."

    # Add task command
    if lower.startswith("add task "):
        return add_task(raw[9:])

    # Show tasks command
    if lower == "show tasks":
        tasks = list_tasks()
        if not tasks:
            return "No tasks found."
        return "Tasks loaded below."

    # Complete task command
    if lower.startswith("complete task "):
        task_part = raw[14:].strip()
        if not task_part.isdigit():
            return "Use: complete task <task_id>"
        return complete_task(int(task_part))

    # Add reminder command
    if lower.startswith("add reminder "):
        payload = raw[13:].strip()
        if " at " in payload:
            content, remind_at = payload.rsplit(" at ", 1)
            return add_reminder(content, remind_at)
        return add_reminder(payload)

    # Show reminders command
    if lower == "show reminders":
        reminders = list_reminders()
        if not reminders:
            return "No reminders found."
        return "Reminders loaded below."

    # Save note command
    if lower.startswith("save note "):
        return add_note(raw[10:])
    
    if lower.startswith("delete reminder "):
        reminder_part = raw[16:].strip()
        if not reminder_part.isdigit():
            return "Use: delete reminder <reminder_id>"
        return delete_reminders([int(reminder_part)])

    # Show notes command
    if lower == "show notes":
        notes = list_notes()
        if not notes:
            return "No notes found."
        return "Notes loaded below."

    # Open quick action command
    if lower.startswith("open "):
        return run_quick_action(raw[5:])

    # Add goal command
    if lower.startswith("add goal "):
        return add_goal(raw[9:])

# Show goals command
    if lower == "show goals":
     goals = list_goals()
     if not goals:
        return "No goals found."
     return "Goals loaded below."

# Complete goal command
    if lower.startswith("complete goal "):
        goal_part = raw[14:].strip()
        if not goal_part.isdigit():
            return "Use: complete goal <goal_id>"
        return update_goal_status(int(goal_part), "completed")

# Pause goal command
    if lower.startswith("pause goal "):
        goal_part = raw[11:].strip()
        if not goal_part.isdigit():
            return "Use: pause goal <goal_id>"
        return update_goal_status(int(goal_part), "paused")

# Resume goal command
    if lower.startswith("resume goal "):
        goal_part = raw[12:].strip()
        if not goal_part.isdigit():
            return "Use: resume goal <goal_id>"
        return update_goal_status(int(goal_part), "in_progress")

# Delete goal command
    if lower.startswith("delete goal "):
        goal_part = raw[12:].strip()
        if not goal_part.isdigit():
            return "Use: delete goal <goal_id>"
        return delete_goal(int(goal_part))


    # Simple summarization command
    if lower.startswith("summarize this:"):
        text = raw.split(":", 1)[1].strip()
        if not text:
            return "Please provide text to summarize."
        return simple_summary(text)

    return (
        "Unknown command. Try one of these: add task ..., show tasks, complete task 1, "
        "add reminder ..., show reminders, save note ..., show notes, open linkedin"
    )


# -----------------------------
# Lightweight text utility
# -----------------------------

# Simple summarization function (takes first 1–2 sentences)
def simple_summary(text: str) -> str:
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    if not sentences:
        return "Nothing to summarize."
    if len(sentences) == 1:
        return f"Summary: {sentences[0]}"
    return f"Summary: {sentences[0]}. {sentences[1]}."


# -----------------------------
# UI
# -----------------------------

# Streamlit page setup
st.set_page_config(page_title="TaskForge Agent", layout="wide")
st_autorefresh(interval=5000, key="reminder_refresh")

st.title("TaskForge Agent")
st.caption(f"Version: {APP_VERSION} | Utility-first local assistant")

st.subheader("Daily Summary")

tasks = list_tasks()
reminders = list_reminders()

pending_tasks = [t for t in tasks if not t["is_done"]]
overdue_tasks = [t for t in tasks if classify_task(t) == "overdue"]
today_tasks = [t for t in tasks if classify_task(t) == "today"]

upcoming_reminders = [r for r in reminders if classify_reminder(r) == "upcoming"]

m1, m2, m3, m4 = st.columns(4)

m1.metric("Pending", len(pending_tasks))
m2.metric("Today", len(today_tasks))
m3.metric("Overdue", len(overdue_tasks))
m4.metric("Upcoming", len(upcoming_reminders))

st.markdown("### Today's Focus")

if overdue_tasks:
    st.warning(f"⚠️ You have {len(overdue_tasks)} overdue tasks")
    for t in overdue_tasks[:3]:
        st.write(f"- {t['content']}")
elif today_tasks:
    st.info("Tasks due today:")
    for t in today_tasks[:3]:
        st.write(f"- {t['content']}")
else:
    st.success("You're clear today. Pick something meaningful.")
# Store last command result
if "command_feedback" not in st.session_state:
    st.session_state.command_feedback = "Ready."
# Goal Status Feedback
if "goal_status_feedback" not in st.session_state:
    st.session_state.goal_status_feedback = " "
# Store currently editing note
if "editing_note_id" not in st.session_state:
    st.session_state.editing_note_id = None
# Select reminders for bulk actions
if "selected_reminders" not in st.session_state:
    st.session_state.selected_reminders = set()
if "selected_tasks" not in st.session_state:
    st.session_state.selected_tasks = set()

# Check due reminders and show toast once
due_reminders = get_due_reminders()
for reminder in due_reminders:
    st.toast(f"Reminder: {reminder['content']}")
    play_alarm_from_file("alarm.mp3")
    mark_reminder_triggered(reminder["id"])
# Command input section
with st.container():
    st.subheader("Command Center")
    command = st.text_input(
        "Enter a command",
        placeholder="Example: add task revise CV",
    )
    if st.button("Run Command", use_container_width=True):
        try:
            st.session_state.command_feedback = agent_router(command)
        except Exception as e:
            st.warning(f"AI failed, using fallback. Error: {e}")
            st.session_state.command_feedback = parse_command(command)
    st.info(st.session_state.command_feedback)

left, right = st.columns(2)

# Left side: Tasks and Notes
with left:
    st.subheader("Tasks")

    with st.form("task_form"):
        task_content = st.text_input("New task")
        submitted_task = st.form_submit_button("Add Task")
        if submitted_task:
            st.success(add_task(task_content))
            st.rerun()

    tasks = list_tasks()
    if tasks:
        for task in tasks:
            done_label = "✅" if task["is_done"] else "⬜"
            status = classify_task(task)

            status_label = ""
            if status == "overdue":
                status_label = " 🔴 OVERDUE"
            elif status == "today":
                status_label = " 🟡 TODAY"
            elif "priority" in task.keys() and task["priority"] == "high":
                status_label = " 🔥 HIGH"
            elif task["is_done"]:
                status_label = " ✅ DONE"

            cols = st.columns([6, 2, 2])

            task_checked = cols[0].checkbox(
                f"{done_label} #{task['id']} — {task['content']}{status_label}",
                key=f"task_select_{task['id']}",
            ) 

            if task_checked:
                st.session_state.selected_tasks.add(task["id"])
            else:
                st.session_state.selected_tasks.discard(task["id"])

            if not task["is_done"]:
                if cols[1].button("Complete", key=f"complete_{task['id']}"):
                    st.success(complete_task(task["id"]))
                    st.rerun()

    selected_task_count = len(st.session_state.selected_tasks)

    if selected_task_count > 0:
        col1, col2 = st.columns(2)

        if col1.button(f"Delete Selected ({selected_task_count})", use_container_width=True):
            result = delete_tasks(list(st.session_state.selected_tasks))
            st.session_state.selected_tasks.clear()

            for task in tasks:
                checkbox_key = f"task_select_{task['id']}"
                if checkbox_key in st.session_state:
                    st.session_state[checkbox_key] = False

            st.success(result)
            st.rerun()

        if col2.button("Clear Selection", use_container_width=True):
            st.session_state.selected_tasks.clear()

            for task in tasks:
                checkbox_key = f"task_select_{task['id']}"
                if checkbox_key in st.session_state:
                    st.session_state[checkbox_key] = False

            st.rerun()
    else:
        st.write("No tasks yet.")

    st.subheader("Notes")

    with st.form("note_form"):
        note_content = st.text_area("Write a short note")
        submitted_note = st.form_submit_button("Save Note")
        if submitted_note:
            st.success(add_note(note_content))
            st.rerun()

    notes = list_notes()
    if notes:
        for note in notes[:10]:
            st.markdown(f"**#{note['id']}** — {note['content']}")
            st.caption(note["created_at"])

            cols = st.columns([1, 1, 4])

            if cols[0].button("Edit", key=f"edit_note_{note['id']}"):
                st.session_state.editing_note_id = note["id"]
                st.rerun()

            if cols[1].button("Delete", key=f"delete_note_{note['id']}"):
                st.success(delete_note(note["id"]))
                if st.session_state.get("editing_note_id") == note["id"]:
                    st.session_state.editing_note_id = None
                st.rerun()

            if st.session_state.get("editing_note_id") == note["id"]:
                with st.form(f"edit_note_form_{note['id']}"):
                    edited_content = st.text_area(
                        "Edit note",
                        value=note["content"],
                        key=f"edit_note_text_{note['id']}",
                    )
                    edit_cols = st.columns(2)
                    save_edit = edit_cols[0].form_submit_button("Save Changes")
                    cancel_edit = edit_cols[1].form_submit_button("Cancel")

                    if save_edit:
                        st.success(update_note(note["id"], edited_content))
                        st.session_state.editing_note_id = None
                        st.rerun()

                    if cancel_edit:
                        st.session_state.editing_note_id = None
                        st.rerun()
    else:
        st.write("No notes yet.")

# Right side: Reminders and Quick Actions
with right:
        # QUICK ACTIONS (also keep inside right!)
    st.subheader("Quick Actions")
    action_cols = st.columns(2)
    if action_cols[0].button("Gmail", use_container_width=True):
        st.success(run_quick_action("gmail"))
    if action_cols[1].button("Notion", use_container_width=True):
        st.success(run_quick_action("notion"))
    if action_cols[0].button("Google Drive", use_container_width=True):
        st.success(run_quick_action("drive"))
    if action_cols[1].button("Google Docs", use_container_width=True):
        st.success(run_quick_action("docs"))
    if action_cols[0].button("Google Calendar", use_container_width=True):
        st.success(run_quick_action("calendar"))
    if action_cols[1].button("Youtube", use_container_width=True):
        st.success(run_quick_action("youtube"))


    st.subheader("Reminders")

    # FORM
    with st.form("reminder_form"):
        reminder_content = st.text_input("Reminder")
        reminder_date = st.date_input("Reminder date", value=date.today())
        reminder_clock = st.time_input(
            "Reminder time",
            value=datetime.now().time().replace(second=0, microsecond=0)
        )
        submitted_reminder = st.form_submit_button("Add Reminder")

        if submitted_reminder:
            if not reminder_content.strip():
                st.error("Reminder content cannot be empty.")
            else:
                reminder_dt = datetime.combine(reminder_date, reminder_clock)
                st.success(add_reminder(
                    reminder_content,
                    reminder_dt.strftime("%Y-%m-%d %H:%M:%S")
                ))
                st.rerun()

    # LIST
    reminders = list_reminders()

    if reminders:
        st.markdown("### Reminder List")

        for r in reminders:
            status = classify_reminder(r)

            label = ""
            if status == "overdue":
                label = " [MISSED]"
            elif status == "upcoming":
                label = " [UPCOMING]"
            elif status == "triggered":
                label = " [DONE]"

            reminder_checked = st.checkbox(
                f"#{r['id']} — {r['content']}{label}",
                key=f"reminder_select_{r['id']}",
            )

            if reminder_checked:
                st.session_state.selected_reminders.add(r["id"])
            else:
                st.session_state.selected_reminders.discard(r["id"])

            if r["remind_at"]:
                st.caption(f"When: {r['remind_at']}")

        selected_count = len(st.session_state.selected_reminders)

        if selected_count > 0:
            col1, col2 = st.columns([1, 1])

            if col1.button(f"Delete Selected ({selected_count})", use_container_width=True):
                result = delete_reminders(list(st.session_state.selected_reminders))
                st.session_state.selected_reminders.clear()

                for r in reminders:
                    checkbox_key = f"reminder_select_{r['id']}"
                    if checkbox_key in st.session_state:
                        st.session_state[checkbox_key] = False

                st.success(result)
                st.rerun()

            if col2.button("Clear Selection", use_container_width=True):
                st.session_state.selected_reminders.clear()

                for r in reminders:
                    checkbox_key = f"reminder_select_{r['id']}"
                    if checkbox_key in st.session_state:
                        st.session_state[checkbox_key] = False

                st.rerun()
    else:
        st.write("No reminders yet.")


# Goal Form       
st.divider()
st.subheader("Goal Mode")

with st.form("goal_form"):
    goal_title = st.text_input("Goal Title")
    goal_desc = st.text_area("Goal Description")
    goal_target_date = st.date_input("Target Date (optional)", value=None)
    submitted_goal = st.form_submit_button("Create Goal")

    if submitted_goal:
        if goal_title.strip():
            target_date_str = (
                goal_target_date.strftime("%Y-%m-%d")
                if goal_target_date is not None
                else None
            )
            st.success(add_goal(goal_title, goal_desc, target_date_str))
            st.rerun()
        else:
            st.error("Goal title cannot be empty.")

goals = list_goals()

if goals:
    st.markdown("### Active Goals")

    for goal in goals[:10]:
        status_badge = ""
        if goal["status"] == "completed":
            status_badge = "✅ COMPLETED"
        elif goal["status"] == "paused":
            status_badge = "⏸️ PAUSED"
        else:
            status_badge = "🎯 IN PROGRESS"

        st.markdown(f"**#{goal['id']} — {goal['title']}**  \n{status_badge}")

        if goal["description"]:
            st.caption(goal["description"])

        meta_parts = [f"Created: {goal['created_at']}"]
        if goal["target_date"]:
            meta_parts.append(f"Target: {goal['target_date']}")
        st.caption(" | ".join(meta_parts))

        if goal["status"] == "in_progress":
            cols = st.columns([1, 1, 4])

            if cols[0].button("Complete", key=f"goal_complete_{goal['id']}"):
                st.session_state.goal_status_feedback = update_goal_status(goal["id"], "completed")
                st.rerun()

            if cols[1].button("Pause", key=f"goal_pause_{goal['id']}"):
                st.session_state.goal_status_feedback = update_goal_status(goal["id"], "paused")
                st.rerun()

        elif goal["status"] == "paused":
            cols = st.columns([1, 1, 4])

            if cols[0].button("Complete", key=f"goal_complete_{goal['id']}"):
                st.session_state.goal_status_feedback = update_goal_status(goal["id"], "completed")
                st.rerun()

            if cols[1].button("Resume", key=f"goal_resume_{goal['id']}"):
                st.session_state.goal_status_feedback = update_goal_status(goal["id"], "in_progress")
                st.rerun()

        elif goal["status"] == "completed":
            cols = st.columns([1, 5])

            if cols[0].button("Delete", key=f"goal_delete_{goal['id']}"):
                st.session_state.goal_status_feedback = delete_goal(goal["id"])
                st.rerun()
    if st.session_state.goal_status_feedback:
        st.info(st.session_state.goal_status_feedback)
else:
    st.write("No goals yet.")
# Command help section
st.divider()
st.markdown(
    """
    **Supported commands**

    - `add task revise CV`
    - `show tasks`
    - `complete task 1`
    - `add reminder apply jobs at 2026-04-05 15:00`
    - `show reminders`
    - `save note ask dad about side job`
    - `show notes`
    - `open linkedin`
    - `summarize this: your text here`
    - `add goal finish portfolio`
    - `show goals`
    - `complete goal 1`
    - `pause goal 1`
    - `resume goal 1`
    - `delete goal 1`
    """
)

# =========================
# SIDEBAR INFO
# =========================
st.sidebar.title("App Info")

st.sidebar.caption(f"Version: {APP_VERSION}")

with st.sidebar.expander("Changelog"):
    st.markdown(load_changelog())

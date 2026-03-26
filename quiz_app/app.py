from __future__ import annotations

import json
import os
import random
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "quiz.db"
QUESTIONS_PATH = BASE_DIR / "perguntas.json"
SECRET_KEY = os.environ.get("SECRET_KEY", "troque-essa-chave-em-producao")
DEV_PASSWORD = os.environ.get("DEV_PASSWORD", "0832")
TOTAL_QUESTIONS = 25
TOTAL_TIME_SECONDS = 240

app = Flask(__name__)
app.config.update(SECRET_KEY=SECRET_KEY)

ELEMENTOS = ["🔥", "🌪️", "⚡", "💧", "🌑"]


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_: Any) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()



def load_questions() -> list[dict[str, Any]]:
    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if len(data) < TOTAL_QUESTIONS:
        raise ValueError(f"É preciso ter pelo menos {TOTAL_QUESTIONS} perguntas em perguntas.json")
    return data



def init_db() -> None:
    db = sqlite3.connect(DB_PATH)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_name TEXT NOT NULL,
            participant_token TEXT NOT NULL,
            score INTEGER NOT NULL,
            wrong_count INTEGER NOT NULL,
            unanswered_count INTEGER NOT NULL,
            elapsed_seconds INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            round_id TEXT NOT NULL,
            answers_json TEXT NOT NULL,
            UNIQUE(participant_token, round_id)
        )
        """
    )
    db.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('quiz_open', '0')"
    )
    db.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('current_round_id', ?) ",
        (uuid.uuid4().hex,),
    )
    db.commit()
    db.close()



def get_setting(key: str) -> str | None:
    row = get_db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None



def set_setting(key: str, value: str) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    db.commit()



def quiz_is_open() -> bool:
    return get_setting("quiz_open") == "1"



def current_round_id() -> str:
    value = get_setting("current_round_id")
    if not value:
        value = uuid.uuid4().hex
        set_setting("current_round_id", value)
    return value



def ensure_participant_token() -> str:
    token = session.get("participant_token")
    if not token:
        token = uuid.uuid4().hex
        session["participant_token"] = token
    return token



def validate_name(name: str) -> str | None:
    stripped = (name or "").strip()
    if len(stripped) < 3:
        return "Seu nome precisa ter pelo menos 3 caracteres."
    if not any(emoji in stripped for emoji in ELEMENTOS):
        return "Insira pelo menos seu elemento no nome: 🔥 🌪️ ⚡ 💧 🌑"
    return None



def participant_already_played(token: str, round_id: str) -> bool:
    row = get_db().execute(
        "SELECT 1 FROM results WHERE participant_token = ? AND round_id = ?",
        (token, round_id),
    ).fetchone()
    return row is not None



def participant_name_already_used(name: str, round_id: str) -> bool:
    row = get_db().execute(
        "SELECT 1 FROM results WHERE lower(participant_name) = lower(?) AND round_id = ?",
        (name.strip(), round_id),
    ).fetchone()
    return row is not None



def quiz_started() -> bool:
    return "quiz_state" in session



def get_quiz_state() -> dict[str, Any] | None:
    return session.get("quiz_state")



def clear_quiz_state() -> None:
    session.pop("quiz_state", None)



def build_quiz_state(name: str) -> dict[str, Any]:
    questions = load_questions()
    chosen = random.sample(questions, TOTAL_QUESTIONS)
    sanitized_questions = []
    answer_key = []
    for q in chosen:
        opcoes_com_indice = list(enumerate(q["options"]))
        random.shuffle(opcoes_com_indice)

        novas_opcoes = [opcao for indice_antigo, opcao in opcoes_com_indice]

        novo_indice_correto = 0
        for novo_indice, (indice_antigo, _) in enumerate(opcoes_com_indice):
            if indice_antigo == int(q["correct_index"]):
                novo_indice_correto = novo_indice
                break

        sanitized_questions.append(
            {
                "question": q["question"],
                "options": novas_opcoes,
            }
        )
        answer_key.append(novo_indice_correto)
    return {
        "name": name.strip(),
        "started_at": int(time.time()),
        "current_index": 0,
        "questions": sanitized_questions,
        "answer_key": answer_key,
        "selected_answers": [],
        "round_id": current_round_id(),
        "finished": False,
        "final_score": None,
    }



def remaining_seconds(state: dict[str, Any]) -> int:
    elapsed = int(time.time()) - int(state["started_at"])
    return max(0, TOTAL_TIME_SECONDS - elapsed)



def finalize_quiz(state: dict[str, Any], timed_out: bool = False) -> int:
    if state.get("finished"):
        return int(state.get("final_score", 0))

    answers = state.get("selected_answers", [])
    key = state.get("answer_key", [])
    score = 0
    wrong = 0
    for idx, selected in enumerate(answers):
        if idx >= len(key):
            break
        if int(selected) == int(key[idx]):
            score += 1
        else:
            wrong += 1
    unanswered = TOTAL_QUESTIONS - len(answers)
    elapsed = TOTAL_TIME_SECONDS - remaining_seconds(state)
    if timed_out:
        elapsed = TOTAL_TIME_SECONDS

    db = get_db()
    db.execute(
        """
        INSERT OR REPLACE INTO results (
            participant_name, participant_token, score, wrong_count, unanswered_count,
            elapsed_seconds, created_at, round_id, answers_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            state["name"],
            ensure_participant_token(),
            score,
            wrong,
            unanswered,
            elapsed,
            int(time.time()),
            state["round_id"],
            json.dumps(answers, ensure_ascii=False),
        ),
    )
    db.commit()

    state["finished"] = True
    state["final_score"] = score
    session["quiz_state"] = state
    return score


@app.route("/")
def index():
    ensure_participant_token()
    return render_template(
        "index.html",
        quiz_open=quiz_is_open(),
        elementos=ELEMENTOS,
    )


@app.post("/start")
def start_quiz():
    if not quiz_is_open():
        return jsonify({"ok": False, "message": "O quiz está fechado no momento."}), 400

    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", ""))
    error = validate_name(name)
    if error:
        return jsonify({"ok": False, "message": error}), 400

    token = ensure_participant_token()
    round_id = current_round_id()

    if participant_already_played(token, round_id):
        return jsonify({"ok": False, "message": "Este dispositivo já participou desta rodada."}), 400

    if participant_name_already_used(name, round_id):
        return jsonify({"ok": False, "message": "Esse nome já foi usado nesta rodada."}), 400

    state = build_quiz_state(name)
    session["quiz_state"] = state
    return jsonify({"ok": True, "redirect": url_for("quiz_page")})


@app.route("/quiz")
def quiz_page():
    state = get_quiz_state()
    if not state:
        return redirect(url_for("index"))

    if state.get("finished"):
        return redirect(url_for("result_page"))

    remaining = remaining_seconds(state)
    if remaining <= 0:
        finalize_quiz(state, timed_out=True)
        return redirect(url_for("result_page"))

    idx = int(state["current_index"])
    if idx >= TOTAL_QUESTIONS:
        finalize_quiz(state)
        return redirect(url_for("result_page"))

    question = state["questions"][idx]
    return render_template(
        "quiz.html",
        participant_name=state["name"],
        question=question,
        current_number=idx + 1,
        total_questions=TOTAL_QUESTIONS,
        remaining_seconds=remaining,
    )


@app.post("/answer")
def answer_question():
    state = get_quiz_state()
    if not state:
        return jsonify({"ok": False, "message": "Sessão do quiz não encontrada."}), 400

    if state.get("finished"):
        return jsonify({"ok": True, "redirect": url_for("result_page")})

    remaining = remaining_seconds(state)
    if remaining <= 0:
        finalize_quiz(state, timed_out=True)
        return jsonify({"ok": True, "redirect": url_for("result_page")})

    payload = request.get_json(silent=True) or {}
    selected_index = payload.get("selected_index")
    if selected_index is None:
        return jsonify({"ok": False, "message": "Selecione uma alternativa."}), 400

    try:
        selected_index = int(selected_index)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "Resposta inválida."}), 400

    current_index = int(state["current_index"])
    options_count = len(state["questions"][current_index]["options"])
    if not (0 <= selected_index < options_count):
        return jsonify({"ok": False, "message": "Resposta fora do intervalo."}), 400

    state["selected_answers"].append(selected_index)
    state["current_index"] = current_index + 1
    session["quiz_state"] = state

    if state["current_index"] >= TOTAL_QUESTIONS:
        finalize_quiz(state)
        return jsonify({"ok": True, "redirect": url_for("result_page")})

    return jsonify({"ok": True, "redirect": url_for("quiz_page")})


@app.route("/result")
def result_page():
    state = get_quiz_state()
    if not state:
        return redirect(url_for("index"))

    if not state.get("finished"):
        finalize_quiz(state, timed_out=remaining_seconds(state) <= 0)

    return render_template(
        "resultado.html",
        participant_name=state["name"],
        score=int(state.get("final_score", 0)),
        total_questions=TOTAL_QUESTIONS,
    )


@app.post("/dev/login")
def dev_login():
    payload = request.get_json(silent=True) or {}
    password = str(payload.get("password", ""))
    if password != DEV_PASSWORD:
        return jsonify({"ok": False, "message": "Senha DEV incorreta."}), 401
    session["dev_logged"] = True
    return jsonify({"ok": True, "redirect": url_for("dev_panel")})



def require_dev() -> None:
    if not session.get("dev_logged"):
        abort(403)


@app.route("/dev")
def dev_panel():
    require_dev()
    db = get_db()
    rows = db.execute(
        """
        SELECT participant_name, score, wrong_count, unanswered_count, elapsed_seconds
        FROM results
        WHERE round_id = ?
        ORDER BY score DESC, elapsed_seconds ASC, participant_name ASC
        """,
        (current_round_id(),),
    ).fetchall()
    return render_template(
        "dev.html",
        quiz_open=quiz_is_open(),
        results=rows,
        current_round_id=current_round_id(),
    )


@app.post("/dev/action")
def dev_action():
    require_dev()
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action", ""))

    if action == "open":
        if quiz_is_open():
            return jsonify({"ok": False, "message": "O quiz já está aberto."}), 400
        set_setting("quiz_open", "1")
        return jsonify({"ok": True, "message": "Quiz aberto com sucesso."})

    if action == "close":
        if not quiz_is_open():
            return jsonify({"ok": False, "message": "O quiz já está fechado."}), 400
        set_setting("quiz_open", "0")
        return jsonify({"ok": True, "message": "Quiz fechado com sucesso."})

    if action == "clear":
        db = get_db()
        db.execute("DELETE FROM results")
        db.commit()
        set_setting("current_round_id", uuid.uuid4().hex)
        set_setting("quiz_open", "0")
        return jsonify({
            "ok": True,
            "message": "Resultados apagados. Nova rodada criada e quiz fechado."
        })

    return jsonify({"ok": False, "message": "Ação inválida."}), 400


@app.route("/dev/logout")
def dev_logout():
    session.pop("dev_logged", None)
    return redirect(url_for("index"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)

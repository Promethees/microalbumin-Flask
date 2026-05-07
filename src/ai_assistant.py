import json
import os
import threading
import requests
from file_path import get_directory
from file import get_file_list
import state

# ── Multilingual system prompts ───────────────────────────────────────────────

_SYSTEM_PROMPTS = {
    "en": (
        "You are OKAPI Assistant, an AI helper built into Easy OKAPI — a local colorimeter "
        "data analysis application for biosensor experiments.\n\n"
        "You help users:\n"
        "- Understand CSV measurement data (absorbance, kinetics, calibration)\n"
        "- Navigate the application workflow (browsing files, generating charts, running regression)\n"
        "- Interpret standard curves, R² values, Michaelis-Menten kinetics, and calibration results\n"
        "- Manage reports and export data\n"
        "- Troubleshoot PyBadge colorimeter hardware connection issues\n\n"
        "Use the available tools to fetch live data from the application when needed.\n"
        "Always respond in English."
    ),
    "vi": (
        "Bạn là OKAPI Assistant, trợ lý AI tích hợp trong Easy OKAPI — ứng dụng phân tích "
        "dữ liệu máy so màu cục bộ dành cho thí nghiệm cảm biến sinh học.\n\n"
        "Bạn hỗ trợ người dùng:\n"
        "- Hiểu dữ liệu CSV (độ hấp thụ, động học, hiệu chuẩn)\n"
        "- Điều hướng quy trình làm việc (duyệt file, tạo biểu đồ, chạy hồi quy)\n"
        "- Giải thích đường chuẩn, giá trị R², động học Michaelis-Menten, kết quả hiệu chuẩn\n"
        "- Quản lý báo cáo và xuất dữ liệu\n"
        "- Xử lý sự cố kết nối phần cứng máy đo màu PyBadge\n\n"
        "Sử dụng các công cụ để lấy dữ liệu thực tế từ ứng dụng khi cần.\n"
        "Luôn trả lời bằng Tiếng Việt."
    ),
    "zh": (
        "您是 OKAPI Assistant，Easy OKAPI 内置的 AI 助手——一款用于生物传感器实验的本地比色计数据分析应用程序。\n\n"
        "您协助用户：\n"
        "- 理解 CSV 测量数据（吸光度、动力学、校准）\n"
        "- 导航应用程序工作流程（浏览文件、生成图表、运行回归）\n"
        "- 解读标准曲线、R² 值、Michaelis-Menten 动力学和校准结果\n"
        "- 管理报告和导出数据\n"
        "- 排除 PyBadge 比色计硬件连接问题\n\n"
        "需要时使用可用工具从应用程序获取实时数据。\n"
        "始终用中文（简体）回答。"
    ),
    "fr": (
        "Vous êtes OKAPI Assistant, un assistant IA intégré dans Easy OKAPI — une application "
        "locale d'analyse de données de colorimètre pour les expériences de biocapteurs.\n\n"
        "Vous aidez les utilisateurs à :\n"
        "- Comprendre leurs données CSV (absorbance, cinétique, calibration)\n"
        "- Naviguer dans le flux de travail de l'application (parcourir les fichiers, générer des graphiques, exécuter des régressions)\n"
        "- Interpréter les courbes étalon, les valeurs R², la cinétique Michaelis-Menten et les résultats de calibration\n"
        "- Gérer les rapports et exporter les données\n"
        "- Dépanner les problèmes de connexion du colorimètre PyBadge\n\n"
        "Utilisez les outils disponibles pour récupérer des données en direct de l'application si nécessaire.\n"
        "Répondez toujours en français."
    ),
    "ja": (
        "あなたは OKAPI Assistant です。Easy OKAPI に内蔵された AI アシスタントで、"
        "バイオセンサー実験向けのローカル比色計データ解析アプリケーションです。\n\n"
        "ユーザーのサポート内容：\n"
        "- CSV 測定データ（吸光度、反応速度論、キャリブレーション）の理解\n"
        "- アプリケーションワークフローの案内（ファイル閲覧、グラフ作成、回帰分析）\n"
        "- 標準曲線、R² 値、Michaelis-Menten 反応速度論、キャリブレーション結果の解釈\n"
        "- レポートの管理とデータのエクスポート\n"
        "- PyBadge 比色計のハードウェア接続トラブルシューティング\n\n"
        "必要に応じて利用可能なツールを使用して、アプリケーションからリアルタイムデータを取得してください。\n"
        "常に日本語で回答してください。"
    ),
    "ru": (
        "Вы — OKAPI Assistant, встроенный ИИ-помощник в Easy OKAPI — локальное приложение "
        "для анализа данных колориметра для биосенсорных экспериментов.\n\n"
        "Вы помогаете пользователям:\n"
        "- Понимать данные CSV (поглощение, кинетика, калибровка)\n"
        "- Навигация по рабочему процессу приложения (просмотр файлов, создание графиков, запуск регрессии)\n"
        "- Интерпретировать стандартные кривые, значения R², кинетику Михаэлиса-Ментена и результаты калибровки\n"
        "- Управлять отчётами и экспортировать данные\n"
        "- Устранять неполадки подключения колориметра PyBadge\n\n"
        "При необходимости используйте доступные инструменты для получения актуальных данных из приложения.\n"
        "Всегда отвечайте на русском языке."
    ),
}

# ── Tool definitions (MCP-style, sent to Ollama) ──────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_app_context",
            "description": (
                "Get the current state of the Easy OKAPI application: "
                "current directory, CSV files, calibration JSON files, and hardware subprocess status."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_csv_file",
            "description": "Read a CSV data file. Returns metadata headers and the first rows of data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "CSV filename (basename only, e.g. 'data.csv').",
                    },
                    "max_rows": {
                        "type": "integer",
                        "description": "Maximum data rows to return (default 30, max 100).",
                        "default": 30,
                    },
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_calibration_file",
            "description": "Read a JSON calibration / standard-curve file from the json/ directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "JSON filename (basename only)."},
                    "mode": {
                        "type": "string",
                        "description": "Subfolder: 'kinetics' or 'point'.",
                        "enum": ["kinetics", "point"],
                    },
                },
                "required": ["filename", "mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_hardware_status",
            "description": "Check whether the PyBadge colorimeter HID subprocess is running.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_help_topic",
            "description": "Return built-in documentation for a specific Easy OKAPI feature or concept.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "enum": [
                            "measurement_modes", "kinetics_analysis", "standard_curve",
                            "calibration", "csv_format", "hardware_setup", "regression",
                            "reports", "file_operations",
                        ],
                    }
                },
                "required": ["topic"],
            },
        },
    },
]

_HELP_DOCS = {
    "measurement_modes": (
        "Easy OKAPI has 3 measurement modes:\n"
        "• kinetics — measures absorbance over time; computes max rate, slope, saturation.\n"
        "• point — single time-point absorbance; used for endpoint assays.\n"
        "• calibrate — applies a saved standard-curve JSON to convert absorbance to concentration."
    ),
    "kinetics_analysis": (
        "Kinetics analysis computes from a sliding-window algorithm:\n"
        "• Max Rate: maximum rate of absorbance change\n"
        "• Slope: overall linear slope\n"
        "• Sat: plateau absorbance value\n"
        "• Time To Sat: time when the reaction plateaus"
    ),
    "standard_curve": (
        "Standard curves relate known concentrations to measured absorbance values.\n"
        "Supported algorithms: linear, polynomial (degree 2-6), logarithmic, exponential, Michaelis-Menten.\n"
        "R² threshold filters out poor fits. Saved as JSON files in json/<mode>/."
    ),
    "calibration": (
        "Calibration converts absorbance to concentrations using a saved standard-curve JSON.\n"
        "Load the JSON via the dropdown, then run calibrate-mode measurements.\n"
        "The app applies stored regression coefficients automatically."
    ),
    "csv_format": (
        "CSV structure:\n"
        "• Metadata lines start with #: Measurement, MeasUnit, TimeUnit, MeasMode\n"
        "• Data header: Timestamp, Value:1, Value:2, …\n"
        "• Calibration CSVs: Concentration, maxRate/Value, Slope, Sat, Time To Sat"
    ),
    "hardware_setup": (
        "PyBadge colorimeter setup:\n"
        "• Mac: hidapi library, run app with sudo for HID access\n"
        "• Windows: install libusbK driver via Zadig, then pyusb\n"
        "• VID/PID: 0x239A / 0x800B (HID) or 0x8034 (serial)\n"
        "• Serial commands via pyserial before spawning the HID logger subprocess"
    ),
    "regression": (
        "Supported regression types:\n"
        "• linear: y = mx + b\n"
        "• polynomial: y = a₀ + a₁x + a₂x² + …\n"
        "• logarithmic: y = a·ln(x) + b\n"
        "• exponential: y = a·e^(bx)\n"
        "• Michaelis-Menten: y = Vmax·x / (Km + x)\n"
        "All computed server-side via scipy.optimize.curve_fit."
    ),
    "reports": (
        "Reports are standalone HTML files saved under report/<subject>/.\n"
        "• 'Generate quick Report' — snapshot current chart\n"
        "• 'Export Data to Report' — push data into a named subject folder\n"
        "Subjects can be renamed, copied, or deleted from the Report panel."
    ),
    "file_operations": (
        "File operations:\n"
        "• Edit — modify CSV/JSON values in a modal editor\n"
        "• Delete — permanently remove files\n"
        "• Copy — duplicate files\n"
        "• Merge CSV — combine multiple CSV files\n"
        "• Remove columns — delete Value columns from CSV\n"
        "• Export — save calibration results to new CSV/JSON"
    ),
}

# ── Model pull state (module-level, single-user app) ─────────────────────────

_pull_state = {
    "active": False,
    "model": "",
    "status": "",
    "total": 0,
    "completed": 0,
    "error": "",
    "done": False,
}
_pull_lock = threading.Lock()


def get_pull_state() -> dict:
    with _pull_lock:
        return dict(_pull_state)


def start_model_pull(ollama_url: str, model: str) -> None:
    """Start an Ollama model pull in a background thread."""
    with _pull_lock:
        if _pull_state["active"]:
            return
        _pull_state.update({"active": True, "model": model, "status": "starting",
                             "total": 0, "completed": 0, "error": "", "done": False})

    def _pull():
        try:
            resp = requests.post(
                f"{ollama_url}/api/pull",
                json={"name": model, "stream": True},
                stream=True,
                timeout=600,
            )
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                except Exception:
                    continue
                with _pull_lock:
                    _pull_state["status"] = data.get("status", _pull_state["status"])
                    if "total" in data:
                        _pull_state["total"] = data["total"]
                    if "completed" in data:
                        _pull_state["completed"] = data["completed"]
                    if data.get("status") == "success":
                        _pull_state["done"] = True
        except Exception as e:
            with _pull_lock:
                _pull_state["error"] = str(e)
                _pull_state["done"] = True
        finally:
            with _pull_lock:
                _pull_state["active"] = False

    threading.Thread(target=_pull, daemon=True).start()


# ── Tool execution ────────────────────────────────────────────────────────────

def _run_tool(name: str, args: dict) -> str:
    try:
        if name == "get_app_context":
            directory = get_directory()
            csv_files = get_file_list(directory)
            json_k = get_file_list(os.path.join(state.json_root_path, "kinetics"), "*.json")
            json_p = get_file_list(os.path.join(state.json_root_path, "point"), "*.json")
            running = state.process is not None and state.process.poll() is None
            return json.dumps({
                "current_directory": os.path.abspath(directory),
                "csv_files": csv_files,
                "json_calibration_kinetics": json_k,
                "json_calibration_point": json_p,
                "hardware_subprocess_running": running,
            }, ensure_ascii=False)

        elif name == "read_csv_file":
            filename = args.get("filename", "")
            max_rows = min(int(args.get("max_rows", 30)), 100)
            filepath = os.path.join(get_directory(), filename)
            if not os.path.exists(filepath):
                return json.dumps({"error": f"'{filename}' not found in current directory."})
            lines = []
            data_rows = 0
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped = line.rstrip()
                    lines.append(stripped)
                    if not stripped.startswith('#'):
                        data_rows += 1
                    if data_rows >= max_rows + 1:
                        break
            return json.dumps({"filename": filename, "content": "\n".join(lines)}, ensure_ascii=False)

        elif name == "read_calibration_file":
            filename = args.get("filename", "")
            mode = args.get("mode", "kinetics")
            filepath = os.path.join(state.json_root_path, mode, filename)
            if not os.path.exists(filepath):
                return json.dumps({"error": f"'{filename}' not found in json/{mode}/."})
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return json.dumps(data, ensure_ascii=False)

        elif name == "get_hardware_status":
            running = state.process is not None and state.process.poll() is None
            return json.dumps({
                "subprocess_running": running,
                "pid": state.process.pid if running else None,
            })

        elif name == "get_help_topic":
            topic = args.get("topic", "")
            doc = _HELP_DOCS.get(topic, "Topic not found.")
            return json.dumps({"topic": topic, "content": doc})

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Chat ──────────────────────────────────────────────────────────────────────

def chat(messages: list, language: str, ollama_url: str, model: str) -> dict:
    """Send a chat request to Ollama, executing any tool calls, and return the final reply."""
    system_prompt = _SYSTEM_PROMPTS.get(language, _SYSTEM_PROMPTS["en"])
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    for _ in range(6):  # guard against infinite tool loops
        try:
            resp = requests.post(
                f"{ollama_url}/api/chat",
                json={"model": model, "messages": full_messages, "tools": TOOLS, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            return {"error": "ollama_offline"}
        except requests.exceptions.Timeout:
            return {"error": "timeout"}
        except Exception as e:
            return {"error": str(e)}

        result = resp.json()
        assistant_msg = result.get("message", {})
        tool_calls = assistant_msg.get("tool_calls") or []

        if not tool_calls:
            return {"reply": assistant_msg.get("content", "")}

        # Execute tool calls and feed results back
        full_messages.append(assistant_msg)
        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_result = _run_tool(fn.get("name", ""), fn.get("arguments") or {})
            full_messages.append({"role": "tool", "content": tool_result})

    return {"error": "max_iterations"}


def check_ollama(ollama_url: str) -> dict:
    """Return {'running': bool, 'models': [...]} for the given Ollama URL."""
    try:
        resp = requests.get(f"{ollama_url}/api/tags", timeout=3)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        return {"running": True, "models": models}
    except Exception:
        return {"running": False, "models": []}

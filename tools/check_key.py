"""检查 .env 里的 API key 是否可用，并列出账号能访问的模型。

    python tools/check_key.py

它会：
  1. 确认读到了哪个供应商的 key（只显示前后几位，不打印完整 key）
  2. 列出这个 key 可用的模型 id
  3. 用 config.py 里配置的三个模型各发一次极短请求，验证名字有效
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import config  # noqa: E402

BAR = "=" * 62

print(BAR)
if config.USE_MOCK and not config.LLM_API_KEY:
    print("没有读到任何 API key。")
    print(f"请把 key 填进：{ROOT / '.env'}")
    print("Groq 用户填    GROQ_API_KEY=gsk_你的key")
    print("Gemini 用户填  GEMINI_API_KEY=AIza你的key")
    print("（等号两边不要有空格和引号）")
    sys.exit(1)

k = config.LLM_API_KEY
print(f"供应商：{config.LLM_PROVIDER}")
if config.LLM_BASE_URL:
    print(f"接口地址：{config.LLM_BASE_URL}")
print(f"读到 key：{k[:6]}…{k[-4:]}（长度 {len(k)}）")
if config.FORCE_MOCK:
    print("注意：.env 里 FORCE_MOCK=1，程序仍会走离线 mock。改成 0 才会真的调用。")
print(BAR)

TARGETS = [
    ("CLIENT_MODEL", config.CLIENT_MODEL),
    ("COUNSELOR_MODEL", config.COUNSELOR_MODEL),
    ("SUPERVISOR_MODEL", config.SUPERVISOR_MODEL),
]


def check_gemini() -> bool:
    try:
        from google import genai
    except ImportError:
        print("缺少 SDK。先运行：pip install google-genai")
        sys.exit(1)

    client = genai.Client(api_key=k)

    print("\n你的 key 可以访问的模型：")
    try:
        for m in client.models.list():
            name = m.name.replace("models/", "")
            actions = getattr(m, "supported_actions", None) or []
            if not actions or "generateContent" in actions:
                print("   " + name)
    except Exception as exc:  # noqa: BLE001
        print(f"   列表拉取失败：{exc}")

    print("\n实际测试 config.py 里配置的三个模型：")
    ok = True
    for label, model in TARGETS:
        try:
            r = client.models.generate_content(
                model=model, contents="Reply with the single word: ok"
            )
            print(f"   OK    {label} = {model}   -> {(r.text or '').strip()[:40]}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"   FAIL  {label} = {model}")
            print(f"         {str(exc)[:200]}")
    return ok


def check_openai_compat() -> bool:
    sys.path.insert(0, str(ROOT / "backend"))
    from llm import openai_compat  # noqa: E402

    print("\n你的 key 可以访问的模型：")
    try:
        for name in openai_compat.list_models():
            print("   " + name)
    except Exception as exc:  # noqa: BLE001
        print(f"   列表拉取失败：{str(exc)[:200]}")

    print("\n实际测试 config.py 里配置的三个模型：")
    ok = True
    for label, model in TARGETS:
        try:
            text = openai_compat.raw_call(
                model,
                "You are a test harness. Answer in one word.",
                [{"role": "user", "text": "Reply with the single word: ok"}],
                json_mode=False,
            )
            print(f"   OK    {label} = {model}   -> {text[:40]}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"   FAIL  {label} = {model}")
            print(f"         {str(exc)[:200]}")
    return ok


ok = check_gemini() if config.LLM_PROVIDER == "gemini" else check_openai_compat()

if not ok:
    print("\n有模型名无效。从上面的可用列表里挑一个，在 .env 里写")
    print("   COUNSELOR_MODEL=你挑的名字")
    print("再跑一次本脚本。")
    sys.exit(1)

print("\n全部通过 —— 直接启动服务就是真实 LLM 模式了：")
print("   python -m uvicorn backend.main:app --reload --port 8000")

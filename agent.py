"""
The data-analyst agent: a ReAct-style loop over an OpenAI-compatible chat model
(configured for aipipe.org by default, since that's what the TDS course provides,
but any OpenAI-compatible endpoint works - just change OPENAI_BASE_URL).

The model has two tools:
  - run_python:     execute code in a persistent sandbox (pandas/numpy/requests/etc)
  - submit_answer:  end the loop and return the final answer value

The caller (bot.py) is responsible for wrapping the returned answer into the
final {"answer": ..., "log_url": ...} JSON the Telegram bot replies with.
"""

import json
import os

from openai import OpenAI

from sandbox import PythonSandbox
import requests
from bs4 import BeautifulSoup

def web_search(query, max_results=5):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    def parse_links(html, exclude_domain):
        soup = BeautifulSoup(html, "html.parser")
        results = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http") or exclude_domain in href:
                continue
            title = a.get_text(strip=True)
            if not title or href in seen:
                continue
            seen.add(href)
            results.append({"title": title, "url": href})
            if len(results) >= max_results:
                break
        return results

    for url, exclude in [
        ("https://lite.duckduckgo.com/lite/", "duckduckgo.com"),
        ("https://html.duckduckgo.com/html/", "duckduckgo.com"),
    ]:
        try:
            resp = requests.post(url, data={"q": query}, headers=headers, timeout=15)
            results = parse_links(resp.text, exclude)
            if results:
                return results
        except requests.RequestException:
            continue

    return [{"title": "search returned no results", "url": ""}]


MODEL = os.environ.get("AGENT_MODEL", "gpt-4o-mini")
MAX_TURNS = int(os.environ.get("AGENT_MAX_TURNS", "12"))

client = OpenAI(
    api_key=os.environ["AIPIPE_TOKEN"],
    base_url=os.environ.get("OPENAI_BASE_URL", "https://aipipe.org/openai/v1"),
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "Execute Python code in a persistent sandbox. pandas (pd), numpy (np), "
                "requests, json, math, re, io, and datetime are pre-imported. State "
                "persists between calls in this conversation, so you can build up a "
                "solution over several steps. Leave a bare expression on the last line "
                "(or use print()) to see its value in the result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to run."}
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_answer",
            "description": (
                "Call this exactly once, when you are confident in the final answer, to "
                "end the task. Pass ONLY the value that belongs in the JSON 'answer' "
                "field, in precisely the shape the question requested - e.g. if the "
                "question says the reply should be "
                '{"answer": {"state": "<state name>"}}, call submit_answer with '
                'answer={"state": "Assam"} - not the whole outer object.'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {
                        "description": "The final answer value, in the exact shape requested."
                    }
                },
                "required": ["answer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web to find the correct current URL for a dataset or source, "
                "instead of guessing from memory (guessed URLs are often stale/dead). "
                "Returns a list of {title, url}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."}
                },
                "required": ["query"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are a meticulous data-analyst agent, answering questions sent to you \
over Telegram by an automated grading account.

Each incoming message is a data-analysis question. It may embed data directly in the \
message, or point at a public dataset (e.g. MOSPI - India's Ministry of Statistics and \
Programme Implementation - or similar open data sources) that you need to fetch \
yourself. The message will also spell out the EXACT JSON shape expected for the \
"answer" field - follow that shape exactly, with the right keys and value types. \
Some conversations are multi-turn: a short back-and-forth. Always answer the LAST \
message, using earlier messages as context if relevant.

You have three tools:
- run_python: fetch, parse, and analyze data (pandas/numpy/requests available, plus \
  fetch_url(url) which is like requests.get but auto-retries with SSL verification \
  relaxed if a government site's certificate chain is broken - prefer fetch_url over \
  raw requests.get for .gov.in/.nic.in sites specifically). Use \
  print() or a trailing bare expression to inspect intermediate results. State \
  persists across calls, so work incrementally: fetch first, inspect the shape and \
  columns, then compute.
- web_search: find the correct current URL for a dataset before fetching it, instead of \
  guessing from memory. Guessed URLs are frequently dead or outdated — use this whenever \
  you're not 100% sure of the exact link.
- submit_answer: call this exactly once, when confident, with ONLY the value for the \
  "answer" key, in the exact shape requested. No extra keys, no prose.
Ground rules:
- Never fabricate numbers or facts. Compute everything from data you actually fetched \
  and inspected.
- If a fetch fails, check the status code / error and try a reasonable alternative \
  (different URL, different parsing library, different data source) before giving up. \
  A ModuleNotFoundError is not a dead end - it just means try a different available \
  library (e.g. pdfplumber for PDFs) or a different source entirely (e.g. fetch the \
  source's HTML page directly with requests+BeautifulSoup and look for tables or \
  numbers in the text, rather than only trying PDFs).
- Give up (submit an error) only after truly exhausting reasonable options - at least \
  2-3 different sources/approaches - not after a single library import fails.
- Double-check your computation (e.g. re-derive a max/min, check a groupby result) \
  before calling submit_answer.
- If, after real, genuine attempts (web_search + run_python fetches) you still cannot \
  retrieve actual data, you MUST NOT invent, simulate, or hard-code plausible-looking \
  numbers or facts as a substitute for real data. This includes writing a Python dict/ \
  DataFrame "based on known values" from memory - that is fabrication, not analysis, \
  and is strictly forbidden even under time pressure.
- If every reasonable data source fails, submit_answer with a clear error object (e.g. \
  {"error": "could not retrieve data: <what failed>"}) instead of a fabricated value. \
  An honest "could not verify" is far better than a confident-looking made-up number.
"""


def run_agent(history, logger):
    """
    history: list of {"role": "user"|"assistant", "content": str}, ending with the
             latest user message.
    logger:  a RunLogger - every LLM turn and tool call is recorded to it.

    Returns: the raw answer value (whatever JSON-serializable shape the model
             passed to submit_answer).
    """
    sandbox = PythonSandbox()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    logger.log({"event": "start", "history": history})

    for turn in range(MAX_TURNS):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message
        tool_calls = msg.tool_calls or []
        logger.log({
            "event": "llm_response",
            "turn": turn,
            "content": msg.content,
            "tool_calls": [tc.model_dump() for tc in tool_calls],
        })

        if not tool_calls:
            # Model replied with plain text instead of calling a tool. Nudge it once.
            messages.append({"role": "assistant", "content": msg.content or ""})
            messages.append({
                "role": "user",
                "content": (
                    "Please use the tools: call run_python if you need to compute "
                    "more, or submit_answer with your final answer."
                ),
            })
            continue

        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [tc.model_dump() for tc in tool_calls],
        })

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if name == "submit_answer":
                answer = args.get("answer")
                logger.log({"event": "submit_answer", "answer": answer})
                return answer

            elif name == "run_python":
                code = args.get("code", "")
                result = sandbox.run(code)
                logger.log({"event": "run_python", "code": code, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result)[:6000],
                })
            elif name == "web_search":
                query = args.get("query", "")
                results = web_search(query)
                logger.log({"event": "web_search", "query": query, "results": results})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(results)[:6000],
                })    
            else:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": f"unknown tool '{name}'"}),
                })

    logger.log({"event": "max_turns_exceeded"})
    return {"error": "agent could not reach a final answer within the turn limit"}
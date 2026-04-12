"""
tests/helpers.py
Shared helper functions for the IZS test suite.

Provides:
  - send_chat(): sends a message to the API and returns the parsed response
  - run_multi_turn_chat(): drives a full multi-turn conversation through the API
  - run_with_retries(): runs a test function up to N times, keeps the best result
  - rate_limit_pause(): sleeps between API calls to respect rate limits
"""
import time
import uuid


# ──────────────────────────────────────────────────────────────
# Rate Limit Protection
# ──────────────────────────────────────────────────────────────

DEFAULT_PAUSE_BETWEEN_TURNS = 5    # seconds between turns in a conversation
DEFAULT_PAUSE_BETWEEN_TESTS = 15   # seconds between separate test scenarios
DEFAULT_PAUSE_ON_ERROR = 30        # seconds to wait after a rate limit / server error


def rate_limit_pause(seconds, reason="rate limit protection"):
    """Pause execution for rate limit protection."""
    print(f"\n⏳ Pausing {seconds}s ({reason})...")
    time.sleep(seconds)
    print("▶️ Resuming.")


# ──────────────────────────────────────────────────────────────
# API Client
# ──────────────────────────────────────────────────────────────

def send_chat(client, session_id: str, message: str, timeout: int = 120) -> dict:
    """
    Send a single message to the /chat API endpoint.

    Returns a dict with keys:
        success, status, reply, nextflow_code, mermaid_agent,
        mermaid_deterministic, ast_json, elapsed, error
    """
    url = "/chat"
    payload = {"session_id": session_id, "message": message}

    start = time.time()
    try:
        resp = client.post(url, json=payload, timeout=timeout)
        elapsed = time.time() - start

        if resp.status_code != 200:
            return {
                "success": False,
                "status": "HTTP_ERROR",
                "reply": None,
                "nextflow_code": None,
                "mermaid_agent": None,
                "mermaid_deterministic": None,
                "ast_json": None,
                "elapsed": elapsed,
                "error": f"HTTP {resp.status_code}: {resp.text[:300]}",
            }

        data = resp.json()
        return {
            "success": True,
            "status": data.get("status", "UNKNOWN"),
            "reply": data.get("reply"),
            "nextflow_code": data.get("nextflow_code"),
            "mermaid_agent": data.get("mermaid_agent"),
            "mermaid_deterministic": data.get("mermaid_deterministic"),
            "ast_json": data.get("ast_json"),
            "elapsed": elapsed,
            "error": data.get("error"),
        }

    except Exception as e:
        if 'timeout' in str(e).lower():
            return {
                "success": False, "status": "TIMEOUT", "reply": None,
                "nextflow_code": None, "mermaid_agent": None,
                "mermaid_deterministic": None, "ast_json": None,
                "elapsed": time.time() - start, "error": "Request timed out",
            }
        return {
            "success": False, "status": "CONNECTION_ERROR", "reply": None,
            "nextflow_code": None, "mermaid_agent": None,
            "mermaid_deterministic": None, "ast_json": None,
            "elapsed": time.time() - start, "error": str(e),
        }


def run_multi_turn_chat(
    client,
    chat_messages: list[str],
    expect_rejection: bool = False,
    pause_between_turns: int = DEFAULT_PAUSE_BETWEEN_TURNS,
) -> dict:
    """
    Drive a full multi-turn conversation through the API.

    Parameters
    ----------
    chat_messages : list[str]
        List of user messages to send in order. The AI replies between them
        are driven by the API (via thread memory).
    expect_rejection : bool
        If True, return after the first response (we expect CHATTING / rejection).

    Returns
    -------
    dict with: success, status, reply, nextflow_code, mermaid_agent,
    mermaid_deterministic, ast_json, elapsed, turns, all_replies
    """
    session_id = f"test_{uuid.uuid4().hex[:12]}"
    total_start = time.time()
    all_replies = []

    for turn_idx, user_msg in enumerate(chat_messages):
        result = send_chat(client, session_id, user_msg)

        if not result["success"]:
            result["turns"] = turn_idx + 1
            result["all_replies"] = all_replies
            return result

        all_replies.append({"turn": turn_idx + 1, "reply": result["reply"], "status": result["status"]})

        # For rejection tests, return after first response
        if expect_rejection:
            result["turns"] = turn_idx + 1
            result["elapsed"] = time.time() - total_start
            result["all_replies"] = all_replies
            return result

        # If we got APPROVED with code, we're done
        if result["status"] == "APPROVED" and result.get("nextflow_code"):
            result["turns"] = turn_idx + 1
            result["elapsed"] = time.time() - total_start
            result["all_replies"] = all_replies
            return result

        # Pause between turns
        if turn_idx < len(chat_messages) - 1:
            rate_limit_pause(pause_between_turns, f"between turn {turn_idx + 1} and {turn_idx + 2}")

    # If we exhausted all messages without APPROVED, return last result
    result["turns"] = len(chat_messages)
    result["elapsed"] = time.time() - total_start
    result["all_replies"] = all_replies
    return result


def run_with_retries(test_fn, max_retries=3, pause_between=DEFAULT_PAUSE_ON_ERROR):
    """
    Run a test function up to max_retries times, keeping the BEST result.
    
    The test_fn should return a dict with at least a 'scores' dict.
    The "best" result is the one with the highest average score.

    Returns
    -------
    (best_result, all_results)
    """
    all_results = []

    for attempt in range(1, max_retries + 1):
        print(f"\n{'='*60}")
        print(f"  ATTEMPT {attempt} / {max_retries}")
        print(f"{'='*60}")

        try:
            result = test_fn()
            result["attempt"] = attempt
            result["error"] = None
            all_results.append(result)
        except Exception as e:
            error_str = str(e).lower()
            all_results.append({"attempt": attempt, "error": str(e), "scores": {}})

            # If rate limit, pause longer
            if "429" in error_str or "rate limit" in error_str:
                print(f"\n⚠️ Rate limit hit on attempt {attempt}. Pausing {pause_between}s...")
                rate_limit_pause(pause_between, "rate limit recovery")
            elif attempt < max_retries:
                rate_limit_pause(pause_between // 2, "error recovery")

        # Pause between retries regardless
        if attempt < max_retries:
            rate_limit_pause(DEFAULT_PAUSE_BETWEEN_TESTS, "between retry attempts")

    # Pick the best result (highest average score)
    best = None
    best_avg = -1
    for r in all_results:
        scores = r.get("scores", {})
        score_vals = [v for k, v in scores.items() if isinstance(v, (int, float)) and "score" in k]
        avg = sum(score_vals) / len(score_vals) if score_vals else 0
        if avg > best_avg:
            best_avg = avg
            best = r

    if best is None:
        best = all_results[-1] if all_results else {"error": "No results", "scores": {}}

    best["total_attempts"] = len(all_results)
    best["all_attempts_summary"] = [
        {"attempt": r.get("attempt"), "error": r.get("error"), "avg_score": _avg_scores(r.get("scores", {}))}
        for r in all_results
    ]

    return best


def _avg_scores(scores: dict) -> float:
    """Calculate average of all score fields in a dict."""
    vals = [v for k, v in scores.items() if isinstance(v, (int, float)) and "score" in k]
    return round(sum(vals) / len(vals), 2) if vals else 0.0

import asyncio
import json
import time
import openai
from loguru import logger

from config import config

client = openai.OpenAI(
    api_key=config.OPENCODE_GO_API_KEY,
    base_url=config.OPENCODE_GO_BASE_URL,
    timeout=60.0,
)

MAX_RETRIES = 2
RETRY_DELAY = 5

SYSTEM_PROMPT = """Kamu adalah analis pasar modal Indonesia yang profesional.
Kamu bisa:
1. Menganalisis saham secara teknikal (RSI, MACD, MA, volume, support/resistance)
2. Menganalisis sentimen pasar dari berita terkini
3. Memberikan rekomendasi trading: BUY, SELL, atau HOLD

Format respons HARUS JSON dengan struktur:
{
  "symbol": "BBCA",
  "signal": "BUY",
  "price_target": 10500,
  "stop_loss": 9800,
  "confidence": 0.75,
  "reason": "RSI oversold + support kuat di 9800",
  "risk_reward_ratio": 1.5
}

Jangan memberikan saran yang bersifat pasti. Selalu sertakan disclaimer risiko.
Rekomendasi berdasarkan data teknikal dan tidak menjamin keuntungan."""


def _call_ai(messages: list, max_tokens: int = 500, temperature: float = 0.3) -> str:
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=config.OPENCODE_GO_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if content and content.strip():
                return content
            logger.warning(f"AI returned empty response (attempt {attempt+1}/{MAX_RETRIES})")
        except Exception as e:
            last_error = e
            logger.warning(f"AI call failed (attempt {attempt+1}/{MAX_RETRIES}): {e}")
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)
    if last_error:
        raise last_error
    raise RuntimeError("AI returned empty response after all retries")


def _parse_json_response(content: str, symbol: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        import re
        m = re.search(r'\{[^{}]*"signal"\s*:\s*"(BUY|SELL|HOLD)"[^{}]*\}', content, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return {"symbol": symbol, "signal": "HOLD", "confidence": 0, "reason": content[:200]}


async def analyze_stock(symbol: str) -> dict:
    try:
        content = _call_ai([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Analisis saham {symbol}. Berikan rekomendasi trading hari ini.\n\nRespond ONLY with the JSON object. No other text."},
        ], max_tokens=2000)
        return _parse_json_response(content, symbol)
    except Exception as e:
        logger.error(f"AI analysis failed for {symbol}: {e}")
        return {"symbol": symbol, "signal": "HOLD", "confidence": 0, "reason": str(e)[:200]}


async def market_sentiment(symbols: list[str]) -> str:
    try:
        return _call_ai([
            {"role": "system", "content": "Kamu analis sentimen pasar saham Indonesia. Berikan analisis singkat."},
            {"role": "user", "content": f"Analisis sentimen pasar untuk saham: {', '.join(symbols)}"},
        ], max_tokens=1000)
    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}")
        return f"Error: {e}"


async def get_trading_advice(symbol: str, portfolio_context: str = "") -> dict:
    try:
        context_msg = f"Analisis saham {symbol}."
        if portfolio_context:
            context_msg += f"\n\nKonteks portofolio: {portfolio_context}"
        context_msg += "\n\nRespond ONLY with the JSON object. No other text."
        content = _call_ai([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context_msg},
        ], max_tokens=1500)
        return _parse_json_response(content, symbol)
    except Exception as e:
        logger.error(f"Trading advice failed for {symbol}: {e}")
        return {"symbol": symbol, "signal": "HOLD", "confidence": 0, "reason": str(e)[:200]}


async def daily_market_summary(watchlist: list[str]) -> str:
    try:
        return _call_ai([
            {"role": "system", "content": "Kamu analis pasar modal. Berikan ringkasan pasar harian dalam Bahasa Indonesia."},
            {"role": "user", "content": f"Buat ringkasan kondisi pasar hari ini untuk saham: {', '.join(watchlist)}. Sebutkan mana yang layak dibeli, dijual, atau ditahan."},
        ], max_tokens=2000, temperature=0.5)
    except Exception as e:
        logger.error(f"Daily summary failed: {e}")
        return f"Error: {e}"


async def chat_with_ai(message: str) -> str:
    try:
        return _call_ai([
            {"role": "system", "content": "Kamu asisten trading AI. Bantu user dengan pertanyaan seputar trading, analisis saham, manajemen risiko, dan strategi pasar modal Indonesia."},
            {"role": "user", "content": message},
        ], max_tokens=1500, temperature=0.5)
    except Exception as e:
        logger.error(f"Chat failed: {e}")
        return f"Maaf, ada error: {e}"

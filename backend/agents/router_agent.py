"""
agents/router_agent.py
----------------------
PURPOSE:
    The RouterAgent is the "front door" of the multi-agent system.
    It reads the user's message and uses the LLM to decide which department
    agent should answer — without the user needing to pick a department manually.

CONCEPT — LLM as a Classifier
    Traditional intent classification uses a trained ML model (BERT, SVM, etc.)
    on labelled data. We skip that entirely by asking the LLM itself:
        "Which department does this message belong to? Reply in JSON."
    The LLM's language understanding is already far better than a small classifier,
    and it requires no training data from us.

CONCEPT — Structured JSON Output
    By setting "format": "json" in the Ollama request, the model is constrained
    to return only valid JSON. We parse it with json.loads() and get a typed dict:
        {"department": "hr", "confidence": 0.92, "reason": "leave policy question"}

    This is more reliable than regex-parsing free text because:
      - No risk of the model wrapping the answer in markdown (```json ... ```)
      - We can validate fields and fall back gracefully if any are missing

CONCEPT — Confidence Threshold
    The model returns a self-assessed confidence (0.0–1.0). Low confidence means
    the query is ambiguous or genuinely cross-departmental. Below a threshold
    (default 0.5) we return a special CLARIFICATION_NEEDED result instead of
    guessing — the chat router then asks the user to choose a department.

CONCEPT — Agent Design Pattern: Perceive → Reason → Act
    Perceive: read the user message (and optionally recent session history)
    Reason:   LLM classifies to a department with justification
    Act:      return the routing decision for the caller to execute

ROUTING PROMPT DESIGN:
    The routing prompt lists each department with a one-line description so
    the model understands what each one handles. Clear examples prevent errors:
      HR  → leave, payroll, onboarding, performance
      IT  → access, passwords, software, hardware, VPN
    Ambiguous queries ("I have a question") yield low confidence → clarification.

EXPORTS:
    RouterAgent          — class with .route(message) → RoutingResult
    RoutingResult        — dataclass with department, confidence, reason
    CLARIFICATION_NEEDED — sentinel string returned when confidence is too low
"""

import json
import requests
from dataclasses import dataclass
from core.config import settings
from core.logging_config import get_logger

logger = get_logger(__name__)

# If router confidence falls below this, ask the user to clarify.
CONFIDENCE_THRESHOLD = 0.50

# Sentinel value returned as department when the router cannot decide.
CLARIFICATION_NEEDED = "clarification_needed"

# Department descriptions injected into the routing prompt.
# Keep these short and distinct — the model must differentiate them reliably.
DEPARTMENT_DESCRIPTIONS = {
    "hr": (
        "Human Resources: leave policies, annual/sick/maternity leave, payroll, "
        "onboarding, offboarding, performance reviews, employee benefits, "
        "dress code, workplace conduct"
    ),
    "it": (
        "IT Support: software access requests, VPN, passwords, laptop/hardware issues, "
        "system troubleshooting, cybersecurity policies, software installation, "
        "email setup, IT helpdesk procedures"
    ),
    "finance": (
        "Finance: expense reimbursement, travel claims, purchase orders, invoices, "
        "budget approvals, petty cash, vendor payments, financial compliance, "
        "receipt submission, credit cards"
    ),
    "legal": (
        "Legal & Compliance: contracts, NDAs, data privacy (PDPA/GDPR), "
        "regulatory compliance, intellectual property, legal disputes, "
        "company policies review, whistleblower procedures"
    ),
    "admin": (
        "Administration: office facility booking, meeting rooms, parking, "
        "stationery/supplies procurement, travel arrangements, courier services, "
        "office access cards, general administrative procedures"
    ),
}


@dataclass
class RoutingResult:
    """
    The output of the RouterAgent.

    Attributes:
        department:  Lowercase department name, or CLARIFICATION_NEEDED.
        confidence:  Self-assessed score 0.0–1.0. Below CONFIDENCE_THRESHOLD
                     the result should not be acted upon — ask the user instead.
        reason:      One-sentence justification from the LLM (useful for logs
                     and for showing the user why they were routed this way).
    """
    department: str
    confidence: float
    reason: str


class RouterAgent:
    """
    Uses the LLM in JSON mode to classify a user message to a department.

    The router is stateless — it reads the message and optional history,
    calls Ollama once, and returns a RoutingResult. No FAISS or SQLite needed.

    Attributes:
        model: Ollama model used for classification.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.OLLAMA_MODEL
        logger.info("RouterAgent initialised with model='%s'", self.model)

    def _build_routing_prompt(self) -> str:
        """
        Build the system prompt that instructs the LLM to act as a router.

        The prompt lists all departments with descriptions and specifies the
        exact JSON schema the model must return. Being explicit about the schema
        dramatically reduces parsing errors.

        Returns:
            System prompt string for the Ollama messages array.
        """
        dept_list = "\n".join(
            f'  "{dept}": {desc}'
            for dept, desc in DEPARTMENT_DESCRIPTIONS.items()
        )

        return (
            "You are a message routing assistant for a company's internal chatbot.\n"
            "Your only job is to read the user's message and decide which department "
            "should handle it.\n\n"
            "Available departments and what they handle:\n"
            f"{dept_list}\n\n"
            "Reply with ONLY a JSON object in this exact format:\n"
            '{\n'
            '  "department": "<one of: hr, it, finance, legal, admin>",\n'
            '  "confidence": <float between 0.0 and 1.0>,\n'
            '  "reason": "<one sentence explaining why you chose this department>"\n'
            '}\n\n'
            "Rules:\n"
            "- confidence = 1.0 means you are certain; 0.0 means completely unsure\n"
            "- If the message is a greeting, too vague, or equally applicable to "
            "multiple departments, set confidence below 0.5\n"
            "- Do not add any text outside the JSON object"
        )

    def route(
        self,
        message: str,
        history: list[dict] | None = None,
    ) -> RoutingResult:
        """
        Classify a user message to a department.

        Args:
            message: The user's raw message.
            history: Optional list of prior {"role", "content"} dicts for
                     context-aware routing (e.g. follow-up questions).

        Returns:
            RoutingResult with department, confidence, and reason.
            If the LLM call fails or returns invalid JSON, returns a safe
            fallback result with CLARIFICATION_NEEDED and confidence=0.0.
        """
        logger.info("RouterAgent.route: message='%s...'", message[:60])

        system_prompt = self._build_routing_prompt()

        messages = [{"role": "system", "content": system_prompt}]

        # Inject the last few history turns so the router understands follow-ups.
        # E.g. "What about part-time?" needs prior context to route correctly.
        if history:
            messages.extend(history[-4:])  # last 2 turns (4 messages)

        messages.append({"role": "user", "content": message})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",   # forces valid JSON output
            "think": False,     # suppress reasoning block from gpt-oss model
        }

        try:
            response = requests.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json=payload,
                timeout=30,
            )
            response.raise_for_status()

            raw = response.json()
            content = raw.get("message", {}).get("content", "{}")
            data = json.loads(content)

            department  = str(data.get("department", "")).lower().strip()
            confidence  = float(data.get("confidence", 0.0))
            reason      = str(data.get("reason", "No reason provided"))

            # Validate department is one we know.
            if department not in DEPARTMENT_DESCRIPTIONS:
                logger.warning(
                    "RouterAgent returned unknown department '%s' — defaulting to clarification",
                    department,
                )
                department = CLARIFICATION_NEEDED
                confidence = 0.0

            # Apply confidence threshold.
            if confidence < CONFIDENCE_THRESHOLD:
                logger.info(
                    "RouterAgent confidence %.2f below threshold %.2f — clarification needed",
                    confidence, CONFIDENCE_THRESHOLD,
                )
                department = CLARIFICATION_NEEDED

            result = RoutingResult(
                department=department,
                confidence=confidence,
                reason=reason,
            )
            logger.info(
                "Routing result: dept=%s confidence=%.2f reason='%s'",
                result.department, result.confidence, result.reason,
            )
            return result

        except requests.Timeout:
            logger.error("RouterAgent: Ollama request timed out")
        except requests.RequestException as exc:
            logger.error("RouterAgent: Ollama request failed: %s", exc)
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.error("RouterAgent: Failed to parse LLM response: %s", exc)

        # Safe fallback — ask user to clarify rather than routing to a wrong dept.
        return RoutingResult(
            department=CLARIFICATION_NEEDED,
            confidence=0.0,
            reason="Router encountered an error; please select a department manually.",
        )

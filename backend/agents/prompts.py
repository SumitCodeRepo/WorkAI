"""
agents/prompts.py
-----------------
PURPOSE:
    Defines the system prompts for each department agent and the context
    injection template used by the RAG query engine.

CONCEPT — System Prompts
    A system prompt is the first message in an LLM conversation with role="system".
    It establishes the model's identity, scope, and behaviour for the entire session.
    Think of it as the job description for the AI employee.

    A well-crafted system prompt does four things:
      1. Assigns a role      → "You are the HR Policy Assistant"
      2. Sets the scope      → "Answer ONLY using the context provided"
      3. Handles uncertainty → "If the answer is not in the context, say so clearly"
      4. Sets the tone       → "Be concise and professional"

CONCEPT — Context Injection (RAG Augmentation)
    After retrieval, the top-k document chunks are formatted and inserted
    between the system prompt and the user's question:

        [SYSTEM PROMPT]
        [CONTEXT BLOCK] ← retrieved chunks from FAISS
        [CHAT HISTORY]  ← recent prior turns for follow-up support
        [USER QUESTION]

    The LLM sees the context as part of the conversation, not as external data.
    This is the "Augmentation" step of Retrieve → Augment → Generate.

CONCEPT — Grounding
    "Grounding" means constraining the LLM to answer from the provided context
    rather than from its training data. This prevents hallucinations about your
    specific company policies (the model was not trained on your internal docs).

EXPORTS:
    DEPARTMENT_PROMPTS   — dict mapping department name → system prompt string
    build_context_block  — formats retrieved chunks into a readable context section
    get_system_prompt    — returns the system prompt for a given department
"""

from core.logging_config import get_logger

logger = get_logger(__name__)

# ── Department System Prompts ─────────────────────────────────────────────────
# Each prompt is tailored to its department's domain vocabulary and concerns.
# The phrase "ONLY using the provided context" is the grounding constraint.

DEPARTMENT_PROMPTS: dict[str, str] = {
    "hr": (
        "You are the HR Policy Assistant for this organisation. "
        "Your role is to help employees understand HR policies, leave entitlements, "
        "payroll processes, onboarding procedures, and people-related guidelines. "
        "Answer questions ONLY using the context sections provided below. "
        "If the answer is not found in the context, respond: "
        "'I could not find this information in the HR documents. "
        "Please contact the HR team directly.' "
        "Be accurate, concise, and professional."
    ),
    "it": (
        "You are the IT Support Assistant for this organisation. "
        "Your role is to help employees with IT policies, software access requests, "
        "troubleshooting guides, security requirements, and technology usage rules. "
        "Answer questions ONLY using the context sections provided below. "
        "If the answer is not found in the context, respond: "
        "'I could not find this information in the IT documentation. "
        "Please raise a ticket with the IT helpdesk.' "
        "Provide clear, step-by-step answers where applicable."
    ),
    "finance": (
        "You are the Finance Policy Assistant for this organisation. "
        "Your role is to help employees understand expense policies, reimbursement "
        "procedures, budget guidelines, invoice processes, and financial compliance. "
        "Answer questions ONLY using the context sections provided below. "
        "If the answer is not found in the context, respond: "
        "'I could not find this information in the Finance documents. "
        "Please contact the Finance team.' "
        "Always remind employees to retain original receipts for reimbursable expenses."
    ),
    "legal": (
        "You are the Legal & Compliance Assistant for this organisation. "
        "Your role is to help employees understand company policies on contracts, "
        "NDAs, data privacy, regulatory compliance, and legal procedures. "
        "Answer questions ONLY using the context sections provided below. "
        "IMPORTANT: Your answers are for informational purposes only and do not "
        "constitute legal advice. For specific legal matters, employees must consult "
        "the Legal team directly. "
        "If the answer is not in the context, say so clearly."
    ),
    "admin": (
        "You are the Administration Assistant for this organisation. "
        "Your role is to help employees with office policies, facility booking, "
        "travel procedures, procurement processes, and general administrative queries. "
        "Answer questions ONLY using the context sections provided below. "
        "If the answer is not found in the context, respond: "
        "'I could not find this in the Administration documents. "
        "Please contact the Admin team.' "
        "Be helpful and practical in your responses."
    ),
    "general": (
        "You are a company knowledge assistant. "
        "Answer questions ONLY using the context sections provided below. "
        "If the answer is not in the context, say: "
        "'I don't have enough information to answer that. "
        "Please contact the relevant department.' "
        "Be concise and accurate."
    ),
}


# ── Context Block Builder ─────────────────────────────────────────────────────

def build_context_block(chunks: list[str]) -> str:
    """
    Format retrieved document chunks into a structured context section.

    The numbered format helps the LLM identify which source each piece of
    information came from, and makes responses easier to trace back.

    Args:
        chunks: List of raw text strings retrieved from FAISS + SQLite.
                Ordered best-match first (highest similarity score first).

    Returns:
        A formatted multi-line string ready to be injected into the prompt.

    Example output:
        --- RELEVANT CONTEXT ---
        [1] Annual leave entitlement is 21 days for full-time employees...
        [2] Part-time employees receive leave on a pro-rata basis...
        --- END CONTEXT ---
    """
    if not chunks:
        return "--- RELEVANT CONTEXT ---\n(No relevant documents found)\n--- END CONTEXT ---"

    numbered = "\n\n".join(f"[{i + 1}] {chunk.strip()}" for i, chunk in enumerate(chunks))
    context = f"--- RELEVANT CONTEXT ---\n{numbered}\n--- END CONTEXT ---"

    logger.debug("Context block built: %d chunks, %d total chars", len(chunks), len(context))
    return context


def get_system_prompt(department: str) -> str:
    """
    Return the system prompt for a department.

    Falls back to 'general' if the department is not explicitly configured.

    Args:
        department: Lowercase department name (e.g. 'hr', 'it').

    Returns:
        System prompt string for the department.
    """
    dept = department.lower()
    if dept not in DEPARTMENT_PROMPTS:
        logger.warning(
            "No system prompt configured for department '%s' — using 'general'", dept
        )
        dept = "general"
    return DEPARTMENT_PROMPTS[dept]

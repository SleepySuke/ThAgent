from langchain_core.tools import tool


@tool
def write_draft(subject: str, body: str) -> str:
    """Save a complete email reply draft.

    Use this tool to write the final reply draft. You MUST call this tool
    before finishing — do not just output text in your response.

    Args:
        subject: Email subject line for the reply (without 'Re:' prefix).
        body: The complete email body text with greeting, content, and sign-off.
    """
    return f"DRAFT_SAVED::SUBJECT::{subject}::BODY::{body}"


@tool
def revise_draft(feedback: str, current_draft: str) -> str:
    """Revise an existing draft based on specific feedback.

    Use this when you need to improve a draft based on reviewer criticism.
    Output the revised draft content directly.

    Args:
        feedback: Specific feedback describing what to improve.
        current_draft: The current draft text that needs revision.

    Returns:
        The revised draft text.
    """
    return f"DRAFT_REVISED::FEEDBACK::{feedback}::DRAFT::{current_draft}"

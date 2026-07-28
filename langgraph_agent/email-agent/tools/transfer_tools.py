from langchain_core.tools import tool


@tool
def transfer_to_classifier(reasoning: str) -> str:
    """Route the email to the Classifier specialist to categorize intent and urgency.

    Call this when a new email arrives and needs to be classified.

    Args:
        reasoning: Brief explanation of why you're routing to the Classifier.
    """
    return f"Routing to Classifier: {reasoning}"


@tool
def transfer_to_researcher(reasoning: str) -> str:
    """Route to the Researcher specialist to search knowledge base and bug tracker.

    Call this after classification to gather relevant information for drafting a reply.

    Args:
        reasoning: Brief explanation of why you're routing to the Researcher.
    """
    return f"Routing to Researcher: {reasoning}"


@tool
def transfer_to_draft_writer(reasoning: str) -> str:
    """Route to the Draft Writer specialist to compose or revise a reply draft.

    Call this when research is complete and a draft needs to be written, or when
    a draft needs revision after human review feedback.

    Args:
        reasoning: Brief explanation of why you're routing to the Draft Writer.
    """
    return f"Routing to Draft Writer: {reasoning}"


@tool
def transfer_to_human_review(reasoning: str) -> str:
    """Route to Human Review for final approval before sending the reply.

    Call this when a draft is ready and needs human approval before sending.

    Args:
        reasoning: Brief explanation of why you're routing to Human Review.
    """
    return f"Routing to Human Review: {reasoning}"


@tool
def finish(summary: str) -> str:
    """Complete email processing. Call this when the email has been fully handled
    (reply sent, or determined to be spam/no-reply-needed).

    Args:
        summary: Brief summary of what was done with this email.
    """
    return f"Finished: {summary}"

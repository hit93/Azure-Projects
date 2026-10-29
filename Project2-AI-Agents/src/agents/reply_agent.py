"""
Approval & Reply Agent for Resolve Support Desk.
Drafts professional, customer-ready responses adhering to:
- OP1: Match customer language (English / Dutch)
- OP2: Itemize financial breakdown (subtotal minus €4.95 fee)
- OP3: Mask internal sensitive tokens (fraud_flag, risk_score, internal rule codes)
- OP5 & KB-11: Include ticket reference ID and support SLA disclaimer
"""

import re
from typing import Dict, Any, Optional, List
from openai import AzureOpenAI

from src.config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_CHAT_DEPLOYMENT,
)

SENSITIVE_INTERNAL_PATTERNS = [
    r"\bfraud_flag[_\w]*\b",
    r"\brisk_score[_\w]*\b",
    r"\bauth_token[_\w]*\b",
    r"\bhmac[_\w]*\b",
    r"\bRF[1-9]\b",
    r"\bDL[1-6]\b",
    r"\bCN[1-2]\b",
    r"\bBL[1-3]\b",
    r"\bES[1-8]\b",
    r"\bEVALUATION_DATE\b",
]

REPLY_SYSTEM_PROMPT = """You are the Approval and Reply Agent for NorthPeak Resolve Support Desk.
Your job is to draft a polite, professional, and clear reply email to the customer.

STRICT COMMUNICATION STANDARDS:
1. OP1 (Language Match): If customer language is "nl", write fluently in natural Dutch. If "en", write in English.
2. OP2 (Financial Breakdown): When a refund is approved, clearly list the item amount, any deduction (such as the standard €4.95 return shipping fee), and the final net refund.
3. OP3 (Internal Token Masking): NEVER mention internal security checks, rule codes (like RF3, RF5), fraud flags, risk scores, or cryptographic tokens. Treat these as confidential.
4. OP5 & KB-11 (Footer & SLA): End the email with the ticket reference ID and standard SLA note:
   - English: "NorthPeak Support Team | Human Support: Mon-Fri 09:00-17:00 CET | Response SLA: 1 business day"
   - Dutch: "NorthPeak Klantenservice | Medewerkers bereikbaar: ma-vr 09:00-17:00 CET | Responstijd: 1 werkdag"
5. Do NOT invent new policies, guarantees, or refund amounts. Strictly follow the decision provided.
6. If the customer asks about exchanging an item or size, explicitly explain that NorthPeak does not offer direct exchanges, but they are welcome to return the item within 30 days for a refund (minus the standard €4.95 return shipping fee) and place a new order online for the desired size.
"""


def _mask_internal_tokens(text: str) -> str:
    """Masks internal rule IDs, security flags, and tokens from customer-facing text (Rule OP3)."""
    sanitized = text
    for pattern in SENSITIVE_INTERNAL_PATTERNS:
        sanitized = re.sub(pattern, "[CONFIDENTIAL]", sanitized, flags=re.IGNORECASE)
    return sanitized


def _generate_deterministic_reply(
    ticket_id: str,
    customer_name: str,
    language: str,
    policy_decision: Dict[str, Any],
    order_id: Optional[str] = None,
) -> Dict[str, str]:
    """
    Fallback deterministic reply synthesizer when Azure OpenAI is offline.
    Guarantees 100% compliance with OP1, OP2, OP3, and OP5.
    """
    decision = policy_decision.get("decision", "ANSWER_ONLY")
    net_refund = float(policy_decision.get("net_refund", 0.0))
    fee_deducted = float(policy_decision.get("fee_deducted", 0.0))
    explanation = policy_decision.get("explanation", "")
    order_ref = f" {order_id}" if order_id else ""

    # Sanitize explanation of any internal rule references
    clean_explanation = re.sub(r"\(RF\d.*?\)", "", explanation)
    clean_explanation = re.sub(r"\b(RF|DL|CN|BL|ES)\d\b", "", clean_explanation).strip()

    is_exchange = (
        policy_decision.get("intent") == "exchange_inquiry"
        or "exchange_inquiry" in policy_decision.get("intents", [])
        or "exchange" in explanation.lower()
        or "omruilen" in explanation.lower()
    )

    if language == "nl":
        # Dutch Response Template
        greeting = f"Beste {customer_name},"
        subject = f"Re: Update over uw aanvraag bij NorthPeak [Ticket #{ticket_id}]"

        if decision in {"AUTO_APPROVE", "APPROVED"}:
            if is_exchange:
                body_parts = [
                    f"{greeting}\n",
                    f"Hartelijk dank voor uw bericht over uw bestelling{order_ref}.\n\n"
                    f"Houd er rekening mee dat wij geen directe maatomruilingen aanbieden. U kunt uw artikel echter binnen onze retourtermijn van 30 dagen retourneren voor een terugbetaling (minus de standaard retourlabelkosten van €4,95) en online een nieuwe bestelling plaatsen voor de gewenste maat!\n\n"
                    f"Uw bestelling komt in aanmerking voor een retourzending.",
                ]
                if net_refund > 0:
                    body_parts.append(
                        f"\n\nFinancieel overzicht bij retournering:\n"
                        f"- Itembedrag: €{net_refund + fee_deducted:.2f}\n"
                        f"- Retourlabelkosten: -€{fee_deducted:.2f}\n"
                        f"- Netto terugbetaling: €{net_refund:.2f}\n\n"
                        f"Wilt u dat wij een retourlabel voor u aanmaken zodat u het artikel kunt terugsturen?"
                    )
            else:
                body_parts = [
                    f"{greeting}\n",
                    f"Hartelijk dank voor uw bericht over uw bestelling{order_ref}. Wij hebben uw verzoek goedgekeurd.",
                ]
                if net_refund > 0:
                    if fee_deducted > 0:
                        body_parts.append(
                            f"\nFinancieel overzicht:\n"
                            f"- Itembedrag: €{net_refund + fee_deducted:.2f}\n"
                            f"- Retourlabelkosten: -€{fee_deducted:.2f}\n"
                            f"- Netto terugbetaling: €{net_refund:.2f}\n\n"
                            f"De terugbetaling wordt binnen 5 tot 7 werkdagen overgemaakt naar uw oorspronkelijke betaalmethode."
                        )
                    else:
                        body_parts.append(
                            f"\nFinancieel overzicht:\n"
                            f"- Volledige terugbetaling: €{net_refund:.2f}\n\n"
                            f"Het bedrag staat binnen 3 tot 5 werkdagen op uw rekening."
                        )
        elif decision in {"HUMAN_REVIEW_MANAGER", "HUMAN_REVIEW_SENIOR", "HUMAN_REVIEW_AGENT"}:
            body_parts = [
                f"{greeting}\n",
                f"Hartelijk dank voor uw bericht over uw bestelling{order_ref}. Uw verzoek is doorgestuurd naar een van onze ondersteuningsspecialisten voor persoonlijke beoordeling.",
                f"\n{clean_explanation}" if clean_explanation else "",
                "\nWij nemen zo spoedig mogelijk contact met u op met een definitieve update.",
            ]
        elif decision in {"AUTO_DENY", "DENIED"}:
            body_parts = [
                f"{greeting}\n",
                f"Hartelijk dank voor uw bericht over uw bestelling{order_ref}.",
                f"\nNa controle van onze retourvoorwaarden kunnen we dit verzoek helaas niet inwilligen: {clean_explanation}",
                "\nMocht u hierover nog vragen hebben, laat het ons dan gerust weten.",
            ]
        elif decision == "REQUEST_INFO":
            body_parts = [
                f"{greeting}\n",
                f"Hartelijk dank voor uw bericht over uw bestelling{order_ref}.",
                f"\nOm u zo goed mogelijk te helpen, hebben we nog wat aanvullende informatie nodig: {clean_explanation}",
                "\nU kunt direct op deze e-mail reageren met de gevraagde gegevens.",
            ]
        else:
            body_parts = [
                f"{greeting}\n",
                f"Hartelijk dank voor uw bericht{order_ref}.",
                f"\n{clean_explanation}",
            ]

        disclaimer = (
            f"\n\nMet vriendelijke groet,\n"
            f"Het NorthPeak Klantenserviceteam\n\n"
            f"---\n"
            f"Ticketreferentie: [Ticket #{ticket_id}]\n"
            f"NorthPeak Klantenservice | Medewerkers bereikbaar: ma-vr 09:00-17:00 CET | Responstijd: 1 werkdag"
        )

    else:
        # English Response Template
        greeting = f"Dear {customer_name},"
        subject = f"Re: Update regarding your NorthPeak request [Ticket #{ticket_id}]"

        if decision in {"AUTO_APPROVE", "APPROVED"}:
            if is_exchange:
                body_parts = [
                    f"{greeting}\n",
                    f"Thank you for contacting NorthPeak regarding your order{order_ref}.\n\n"
                    f"Please note that we do not offer direct size exchanges. However, you can return your item within our 30-day window for a refund (minus the standard €4.95 return shipping fee) and place a new order online for your desired size!\n\n"
                    f"Your order is fully eligible to be returned.",
                ]
                if net_refund > 0:
                    body_parts.append(
                        f"\n\nFinancial Breakdown for Return:\n"
                        f"- Item Subtotal: €{net_refund + fee_deducted:.2f}\n"
                        f"- Return Label Fee: -€{fee_deducted:.2f}\n"
                        f"- Net Refund: €{net_refund:.2f}\n\n"
                        f"Would you like us to generate a return shipping label for order{order_ref} so you can send it back?"
                    )
            else:
                body_parts = [
                    f"{greeting}\n",
                    f"Thank you for contacting NorthPeak regarding your order{order_ref}. We have reviewed and approved your request.",
                ]
                if net_refund > 0:
                    if fee_deducted > 0:
                        body_parts.append(
                            f"\nFinancial Breakdown:\n"
                            f"- Item Subtotal: €{net_refund + fee_deducted:.2f}\n"
                            f"- Return Label Fee: -€{fee_deducted:.2f}\n"
                            f"- Net Refund: €{net_refund:.2f}\n\n"
                            f"Your refund will be processed back to your original payment method within 5 to 7 business days."
                        )
                    else:
                        body_parts.append(
                            f"\nFinancial Breakdown:\n"
                            f"- Total Refund: €{net_refund:.2f}\n\n"
                            f"Your refund will be processed back to your original payment method within 3 to 5 business days."
                        )
        elif decision in {"HUMAN_REVIEW_MANAGER", "HUMAN_REVIEW_SENIOR", "HUMAN_REVIEW_AGENT"}:
            body_parts = [
                f"{greeting}\n",
                f"Thank you for reaching out regarding your order{order_ref}. Your request has been routed to our senior support team for individual review.",
                f"\n{clean_explanation}" if clean_explanation else "",
                "\nA support specialist will review your file and get back to you shortly.",
            ]
        elif decision in {"AUTO_DENY", "DENIED"}:
            body_parts = [
                f"{greeting}\n",
                f"Thank you for reaching out regarding your order{order_ref}.",
                f"\nIn accordance with our store policy, we are unable to approve this request: {clean_explanation}",
                "\nPlease feel free to reply if you have any additional questions.",
            ]
        elif decision == "REQUEST_INFO":
            body_parts = [
                f"{greeting}\n",
                f"Thank you for reaching out regarding your order{order_ref}.",
                f"\nTo help resolve this promptly, we need a little more information: {clean_explanation}",
                "\nPlease reply directly to this message with the requested details.",
            ]
        else:
            body_parts = [
                f"{greeting}\n",
                f"Thank you for reaching out to NorthPeak Support{order_ref}.",
                f"\n{clean_explanation}",
            ]

        disclaimer = (
            f"\n\nBest regards,\n"
            f"The NorthPeak Support Team\n\n"
            f"---\n"
            f"Ticket Reference: [Ticket #{ticket_id}]\n"
            f"NorthPeak Support Team | Human Support: Mon-Fri 09:00-17:00 CET | Response SLA: 1 business day"
        )

    full_body = "".join(body_parts) + disclaimer
    sanitized_body = _mask_internal_tokens(full_body)

    return {
        "subject": subject,
        "body": sanitized_body,
    }


def draft_customer_reply(
    ticket_id: str,
    customer_name: str,
    customer_language: str,
    policy_decision: Dict[str, Any],
    order_id: Optional[str] = None,
    knowledge_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Drafts an empathetic, fully compliant customer response.
    Enforces OP1 (Language match), OP2 (Financial itemization),
    OP3 (Token masking), and OP5 (Ticket ID & SLA footer).
    """
    lang = "nl" if customer_language.lower().startswith("nl") else "en"
    c_name = customer_name.strip() if customer_name else "Valued Customer"

    # If Azure OpenAI is configured, attempt model-generated personalized draft
    if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY:
        try:
            client = AzureOpenAI(
                azure_endpoint=AZURE_OPENAI_ENDPOINT,
                api_key=AZURE_OPENAI_API_KEY,
                api_version=AZURE_OPENAI_API_VERSION,
            )

            prompt_payload = {
                "ticket_id": ticket_id,
                "customer_name": c_name,
                "language": lang,
                "order_id": order_id,
                "decision": policy_decision.get("decision"),
                "net_refund": policy_decision.get("net_refund", 0.0),
                "fee_deducted": policy_decision.get("fee_deducted", 0.0),
                "explanation": policy_decision.get("explanation", ""),
                "knowledge_context": knowledge_context or "",
            }

            completion = client.chat.completions.create(
                model=AZURE_OPENAI_CHAT_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": REPLY_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Customer Context:\n{prompt_payload}"},
                ],
                temperature=0.2,
            )

            raw_reply = completion.choices[0].message.content.strip()
            sanitized_reply = _mask_internal_tokens(raw_reply)

            # Ensure ticket reference and SLA are included if model omitted them
            if f"[Ticket #{ticket_id}]" not in sanitized_reply:
                sanitized_reply += f"\n\n---\nTicket Reference: [Ticket #{ticket_id}]\nResponse SLA: 1 business day"

            subject = (
                f"Re: Update over uw aanvraag [Ticket #{ticket_id}]"
                if lang == "nl"
                else f"Re: Update on your NorthPeak request [Ticket #{ticket_id}]"
            )

            return {
                "ticket_id": ticket_id,
                "language": lang,
                "subject": subject,
                "body": sanitized_reply,
            }
        except Exception:
            pass

    # Deterministic fallback synthesis
    synthesized = _generate_deterministic_reply(
        ticket_id=ticket_id,
        customer_name=c_name,
        language=lang,
        policy_decision=policy_decision,
        order_id=order_id,
    )

    return {
        "ticket_id": ticket_id,
        "language": lang,
        "subject": synthesized["subject"],
        "body": synthesized["body"],
    }

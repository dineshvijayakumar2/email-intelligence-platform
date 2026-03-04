"""
Unified Email Rules Service

Normalizes Gmail filters and Outlook inbox rules into a unified format,
computes per-mailbox metrics, and derives cross-AM insights.

No AI cost — pure metric-based analysis.
"""

import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class EmailRulesService:
    """Unified rules normalization + analytics engine."""

    def __init__(self, supabase_client):
        self.client = supabase_client

    # ------------------------------------------------------------------
    # Normalization: Gmail filter → unified format
    # ------------------------------------------------------------------
    def normalize_gmail_filter(
        self, filter_row: dict, mailbox_id: str = "", mailbox_email: str = ""
    ) -> dict:
        """
        Normalize a gmail_filters row into unified rule format.

        Gmail criteria JSONB example:
            {"from": "boss@acme.com", "subject": "urgent", "hasAttachment": true}
        Gmail action JSONB example:
            {"addLabelIds": ["Label_1"], "removeLabelIds": ["INBOX"], "forward": "team@acme.com"}
        """
        criteria = filter_row.get("criteria") or {}
        action = filter_row.get("action") or {}

        # Parse conditions
        from_val = criteria.get("from", "")
        from_addresses = [from_val] if from_val and "@" in from_val else []
        from_domains = [from_val] if from_val and "@" not in from_val and "." in from_val else []
        # If it looks like a domain pattern without @, treat as domain
        if from_val and not from_addresses and not from_domains and from_val:
            from_addresses = [from_val]  # fallback: treat as address

        to_val = criteria.get("to", "")
        to_addresses = [to_val] if to_val else []

        subject_val = criteria.get("subject", "")
        subject_contains = [subject_val] if subject_val else []

        has_attachment = criteria.get("hasAttachment")

        # Parse actions
        label_ids = action.get("addLabelIds", [])
        remove_label_ids = action.get("removeLabelIds", [])
        forward_to = [action["forward"]] if action.get("forward") else []
        skip_inbox = "INBOX" in remove_label_ids
        delete = "TRASH" in (action.get("addLabelIds") or [])
        mark_read = action.get("markAsRead", False)
        mark_important = "IMPORTANT" in label_ids

        # Derive a name from criteria
        name_parts = []
        if from_val:
            name_parts.append(f"From: {from_val}")
        if subject_val:
            name_parts.append(f"Subject: {subject_val}")
        if has_attachment:
            name_parts.append("Has attachment")
        name = " | ".join(name_parts) if name_parts else f"Gmail filter {filter_row.get('filter_id', '')}"

        # Label name (just use label IDs as-is — would need Gmail API to resolve)
        label = ", ".join([lid for lid in label_ids if lid not in ("INBOX", "TRASH", "IMPORTANT")]) or None

        unified = {
            "id": filter_row.get("id"),
            "mailbox_id": mailbox_id,
            "mailbox_email": mailbox_email,
            "source_type": "gmail",
            "source_rule_id": filter_row.get("filter_id", ""),
            "name": name,
            "is_active": filter_row.get("is_active", True),
            "conditions": {
                "from_addresses": from_addresses,
                "from_domains": from_domains,
                "to_addresses": to_addresses,
                "subject_contains": subject_contains,
                "body_contains": [],
                "has_attachment": has_attachment,
            },
            "actions": {
                "label": label,
                "move_to_folder": None,
                "forward_to": forward_to,
                "mark_important": mark_important,
                "mark_read": mark_read,
                "skip_inbox": skip_inbox,
                "delete": delete,
            },
            "engagement_signal": "",  # computed below
            "imported_at": filter_row.get("updated_at"),
        }
        unified["engagement_signal"] = self.derive_engagement_signal(unified)
        return unified

    # ------------------------------------------------------------------
    # Normalization: Outlook rule → unified format
    # ------------------------------------------------------------------
    def normalize_outlook_rule(
        self, rule_row: dict, mailbox_id: str = "", mailbox_email: str = ""
    ) -> dict:
        """
        Normalize an outlook_rules row into unified rule format.

        Outlook conditions JSONB example:
            {"senderContains": ["acme.com"], "subjectContains": ["urgent"],
             "fromAddresses": [{"emailAddress": {"address": "boss@acme.com"}}]}
        Outlook actions JSONB example:
            {"moveToFolder": "AAMkAG...", "forwardTo": [...], "markImportance": "high",
             "markAsRead": true, "delete": false}
        """
        conditions = rule_row.get("conditions") or {}
        actions = rule_row.get("actions") or {}

        # Parse conditions
        from_addresses_raw = conditions.get("fromAddresses", [])
        from_addresses = []
        for addr in from_addresses_raw:
            email = addr.get("emailAddress", {}).get("address", "")
            if email:
                from_addresses.append(email)

        sender_contains = conditions.get("senderContains", [])
        from_domains = [s for s in sender_contains if "." in s and "@" not in s]
        from_addresses.extend([s for s in sender_contains if "@" in s])

        subject_contains = conditions.get("subjectContains", [])
        body_contains = conditions.get("bodyContains", [])
        has_attachment = conditions.get("hasAttachments")

        to_addresses_raw = conditions.get("sentToAddresses", [])
        to_addresses = []
        for addr in to_addresses_raw:
            email = addr.get("emailAddress", {}).get("address", "")
            if email:
                to_addresses.append(email)

        # Parse actions
        forward_to_raw = actions.get("forwardTo", [])
        forward_to = []
        for addr in forward_to_raw:
            email = addr.get("emailAddress", {}).get("address", "")
            if email:
                forward_to.append(email)

        importance = actions.get("markImportance", "")
        mark_important = importance == "high"
        mark_read = actions.get("markAsRead", False)
        delete = actions.get("delete", False)
        move_to_folder = actions.get("moveToFolder")
        skip_inbox = bool(move_to_folder) or delete

        # Outlook has a stop processing flag — treat as-is
        # actions.get("stopProcessingRules", False)

        unified = {
            "id": rule_row.get("id"),
            "mailbox_id": mailbox_id,
            "mailbox_email": mailbox_email,
            "source_type": "outlook",
            "source_rule_id": rule_row.get("rule_id", ""),
            "name": rule_row.get("display_name", f"Outlook rule {rule_row.get('rule_id', '')}"),
            "is_active": rule_row.get("is_enabled", True),
            "conditions": {
                "from_addresses": from_addresses,
                "from_domains": from_domains,
                "to_addresses": to_addresses,
                "subject_contains": subject_contains,
                "body_contains": body_contains,
                "has_attachment": has_attachment,
            },
            "actions": {
                "label": None,
                "move_to_folder": move_to_folder,
                "forward_to": forward_to,
                "mark_important": mark_important,
                "mark_read": mark_read,
                "skip_inbox": skip_inbox,
                "delete": delete,
            },
            "engagement_signal": "",
            "imported_at": rule_row.get("updated_at") or rule_row.get("imported_at"),
        }
        unified["engagement_signal"] = self.derive_engagement_signal(unified)
        return unified

    # ------------------------------------------------------------------
    # Engagement Signal Derivation (from docs section 6.4)
    # ------------------------------------------------------------------
    @staticmethod
    def derive_engagement_signal(unified_rule: dict) -> str:
        """
        Derive engagement signal from normalized rule actions.

        Returns one of: high_value, escalation, low_priority, segmentation, neutral
        """
        actions = unified_rule.get("actions", {})

        # High value: marks important OR label contains VIP/key/priority/strategic
        if actions.get("mark_important"):
            return "high_value"
        label = (actions.get("label") or "").lower()
        if any(kw in label for kw in ["key", "vip", "priority", "important", "strategic"]):
            return "high_value"

        # Escalation: forwards to another address
        if actions.get("forward_to"):
            return "escalation"

        # Low priority: skips inbox OR marks read OR deletes
        if actions.get("skip_inbox") or actions.get("mark_read") or actions.get("delete"):
            return "low_priority"

        # Segmentation: moves to folder OR applies label
        if actions.get("move_to_folder") or actions.get("label"):
            return "segmentation"

        return "neutral"

    # ------------------------------------------------------------------
    # Fetch unified rules for one mailbox
    # ------------------------------------------------------------------
    def get_unified_rules(self, mailbox_id: str) -> list:
        """Get all rules for a single mailbox, normalized to unified format."""
        # Get mailbox info
        mailbox = self._get_mailbox(mailbox_id)
        if not mailbox:
            return []

        mailbox_email = mailbox.get("email_address") or mailbox.get("name", "")
        config = mailbox.get("connection_config") or {}
        live_type = self.get_live_connection_type(mailbox)

        rules = []

        # Resolve user_id — try provider-specific config first, then mailbox owner
        provider_user_id = config.get("gmail_user_id") or config.get("outlook_user_id")
        mailbox_user_id = mailbox.get("user_id", "")
        user_id = provider_user_id or mailbox_user_id

        if not user_id:
            return []

        # Gmail filters — check LIVE connection, not just mailbox_type
        if live_type == "gmail":
            gmail_resp = self.client.table("gmail_filters").select("*").eq(
                "user_id", user_id
            ).execute()
            # Fallback: if config user_id found nothing, try mailbox user_id
            if not gmail_resp.data and provider_user_id and mailbox_user_id and provider_user_id != mailbox_user_id:
                gmail_resp = self.client.table("gmail_filters").select("*").eq(
                    "user_id", mailbox_user_id
                ).execute()
            for row in (gmail_resp.data or []):
                rules.append(self.normalize_gmail_filter(row, mailbox_id, mailbox_email))

        # Outlook rules — check LIVE connection, not just mailbox_type
        if live_type == "outlook":
            outlook_resp = self.client.table("outlook_rules").select("*").eq(
                "user_id", user_id
            ).execute()
            # Fallback: if config user_id found nothing, try mailbox user_id
            if not outlook_resp.data and provider_user_id and mailbox_user_id and provider_user_id != mailbox_user_id:
                outlook_resp = self.client.table("outlook_rules").select("*").eq(
                    "user_id", mailbox_user_id
                ).execute()
            for row in (outlook_resp.data or []):
                rules.append(self.normalize_outlook_rule(row, mailbox_id, mailbox_email))

        return rules

    # ------------------------------------------------------------------
    # Fetch rules for all mailboxes of a client
    # ------------------------------------------------------------------
    def get_all_rules_for_client(self, client_id: str) -> dict:
        """
        Get unified rules for all mailboxes belonging to a client.

        Returns:
            {"rules": [...], "by_mailbox": {mailbox_id: [...]}}
        """
        mailboxes = self._get_client_mailboxes(client_id)
        all_rules = []
        by_mailbox = {}

        for mailbox in mailboxes:
            mb_id = mailbox["id"]
            mb_rules = self.get_unified_rules(mb_id)
            all_rules.extend(mb_rules)
            by_mailbox[mb_id] = mb_rules

        return {"rules": all_rules, "by_mailbox": by_mailbox}

    # ------------------------------------------------------------------
    # Cross-AM Analytics
    # ------------------------------------------------------------------
    def get_rules_analytics(self, client_id: str) -> dict:
        """
        Compute cross-AM rules comparison metrics.

        Returns per-mailbox metrics and aggregate stats.
        """
        data = self.get_all_rules_for_client(client_id)
        mailboxes = self._get_client_mailboxes(client_id)

        mb_lookup = {m["id"]: m for m in mailboxes}
        metrics_list = []
        total_rules = 0
        no_rules_count = 0

        for mailbox in mailboxes:
            mb_id = mailbox["id"]
            mb_rules = data["by_mailbox"].get(mb_id, [])
            mb_email = mailbox.get("email_address") or mailbox.get("name", "")
            mb_type = mailbox.get("mailbox_type", "")
            live_type = self.get_live_connection_type(mailbox)

            # Signal counts
            signal_counts = {"high_value": 0, "escalation": 0, "low_priority": 0, "segmentation": 0, "neutral": 0}
            forward_count = 0
            covered_domains = set()
            covered_addresses = set()
            active_count = 0

            for rule in mb_rules:
                signal = rule.get("engagement_signal", "neutral")
                signal_counts[signal] = signal_counts.get(signal, 0) + 1
                if rule.get("is_active"):
                    active_count += 1

                # Forward count
                fwd = rule.get("actions", {}).get("forward_to", [])
                if fwd:
                    forward_count += 1

                # Covered domains/addresses
                conds = rule.get("conditions", {})
                covered_domains.update(conds.get("from_domains", []))
                covered_addresses.update(conds.get("from_addresses", []))

            metrics = {
                "mailbox_id": mb_id,
                "mailbox_email": mb_email,
                "mailbox_type": mb_type,
                "live_connection": live_type,  # 'gmail', 'outlook', or ''
                "total_rules": len(mb_rules),
                "active_rules": active_count,
                "high_value_count": signal_counts["high_value"],
                "escalation_count": signal_counts["escalation"],
                "low_priority_count": signal_counts["low_priority"],
                "segmentation_count": signal_counts["segmentation"],
                "neutral_count": signal_counts["neutral"],
                "forward_count": forward_count,
                "covered_domains": sorted(covered_domains),
                "covered_addresses": sorted(covered_addresses),
            }
            metrics_list.append(metrics)
            total_rules += len(mb_rules)

            if len(mb_rules) == 0:
                no_rules_count += 1

        total_mailboxes = len(mailboxes)
        avg_rules = total_rules / total_mailboxes if total_mailboxes > 0 else 0.0

        return {
            "mailboxes": metrics_list,
            "total_mailboxes": total_mailboxes,
            "total_rules": total_rules,
            "avg_rules_per_mailbox": round(avg_rules, 1),
            "mailboxes_with_no_rules": no_rules_count,
        }

    # ------------------------------------------------------------------
    # Insights Derivation
    # ------------------------------------------------------------------
    def get_rules_insights(self, client_id: str) -> list:
        """
        Derive actionable insights from cross-AM rules comparison.

        Returns a list of insight dicts with type, severity, description,
        affected mailboxes, and recommendation.
        """
        analytics = self.get_rules_analytics(client_id)
        mailboxes = analytics["mailboxes"]
        insights = []

        if not mailboxes:
            return insights

        # 1. Mailboxes with zero rules
        no_rules = [m for m in mailboxes if m["total_rules"] == 0]
        if no_rules:
            insights.append({
                "insight_type": "no_rules",
                "severity": "warning",
                "description": (
                    f"{len(no_rules)} mailbox(es) have no email rules configured. "
                    f"Email organization helps prioritize conversations."
                ),
                "affected_mailboxes": [m["mailbox_email"] for m in no_rules],
                "recommendation": "Import rules from Gmail/Outlook or create manual rules to organize incoming email.",
            })

        # 2. No escalation rules
        no_escalation = [m for m in mailboxes if m["total_rules"] > 0 and m["escalation_count"] == 0]
        if no_escalation and len(mailboxes) > 1:
            insights.append({
                "insight_type": "no_escalation",
                "severity": "info",
                "description": (
                    f"{len(no_escalation)} mailbox(es) have rules but none forward/escalate emails. "
                    f"Escalation rules ensure critical emails reach the right people."
                ),
                "affected_mailboxes": [m["mailbox_email"] for m in no_escalation],
                "recommendation": "Consider adding forwarding rules for high-priority or urgent emails.",
            })

        # 3. Heavy mark-as-read / delete usage
        heavy_dismiss = []
        for m in mailboxes:
            if m["total_rules"] > 0:
                dismiss_pct = (m["low_priority_count"] / m["total_rules"]) * 100
                if dismiss_pct >= 40:
                    heavy_dismiss.append((m, dismiss_pct))

        if heavy_dismiss:
            for m, pct in heavy_dismiss:
                insights.append({
                    "insight_type": "heavy_low_priority",
                    "severity": "warning",
                    "description": (
                        f"{m['mailbox_email']} marks {pct:.0f}% of rules as "
                        f"low-priority (skip inbox / mark read / delete). "
                        f"This may cause important emails to be missed."
                    ),
                    "affected_mailboxes": [m["mailbox_email"]],
                    "recommendation": "Review low-priority rules to ensure no important contacts or topics are being auto-dismissed.",
                })

        # 4. Best practice template — mailbox with most high-value rules
        has_rules = [m for m in mailboxes if m["total_rules"] > 0]
        if len(has_rules) > 1:
            best = max(has_rules, key=lambda m: m["high_value_count"])
            if best["high_value_count"] > 0:
                others_with_less = [
                    m for m in has_rules
                    if m["mailbox_id"] != best["mailbox_id"] and m["high_value_count"] < best["high_value_count"]
                ]
                if others_with_less:
                    insights.append({
                        "insight_type": "best_practice",
                        "severity": "info",
                        "description": (
                            f"{best['mailbox_email']} has the most high-value rules ({best['high_value_count']}). "
                            f"This could serve as a template for other AMs."
                        ),
                        "affected_mailboxes": [m["mailbox_email"] for m in others_with_less],
                        "recommendation": (
                            f"Review {best['mailbox_email']}'s VIP/priority rules "
                            f"and consider replicating for other mailboxes."
                        ),
                    })

        # 5. Domains covered by some but not all AMs
        all_domains = set()
        domain_coverage = {}  # domain → set of mailbox_emails
        for m in mailboxes:
            for domain in m["covered_domains"]:
                all_domains.add(domain)
                if domain not in domain_coverage:
                    domain_coverage[domain] = set()
                domain_coverage[domain].add(m["mailbox_email"])

        mailboxes_with_rules = [m for m in mailboxes if m["total_rules"] > 0]
        if len(mailboxes_with_rules) > 1:
            for domain, covered_by in domain_coverage.items():
                uncovered = [m["mailbox_email"] for m in mailboxes_with_rules if m["mailbox_email"] not in covered_by]
                if uncovered and len(covered_by) < len(mailboxes_with_rules):
                    insights.append({
                        "insight_type": "partial_domain_coverage",
                        "severity": "info",
                        "description": (
                            f"Domain '{domain}' has rules in {len(covered_by)} mailbox(es) "
                            f"but not in {len(uncovered)} other(s)."
                        ),
                        "affected_mailboxes": uncovered,
                        "recommendation": f"Consider adding rules for '{domain}' in the uncovered mailboxes.",
                    })

        return insights

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def get_live_connection_type(mailbox: dict) -> str:
        """
        Determine the LIVE connection type for a mailbox.

        Checks connection_config for enabled flags + access tokens,
        not just mailbox_type — because archive mailboxes (mbox/pst/olm)
        can be extended with LIVE Gmail/Outlook connections.

        Returns: 'gmail', 'outlook', or '' (no live connection)
        """
        config = mailbox.get("connection_config") or {}
        mailbox_type = mailbox.get("mailbox_type", "")

        # Gmail: native gmail type OR archive extended with gmail
        if config.get("gmail_sync_enabled") and config.get("gmail_access_token"):
            return "gmail"
        if mailbox_type == "gmail":
            return "gmail"  # type is gmail but may lack tokens (auth expired)

        # Outlook: native outlook_live type OR archive extended with outlook
        if config.get("outlook_sync_enabled") and config.get("outlook_access_token"):
            return "outlook"
        if mailbox_type == "outlook_live":
            return "outlook"  # type is outlook but may lack tokens

        return ""

    def _get_mailbox(self, mailbox_id: str) -> Optional[dict]:
        """Fetch a single mailbox record."""
        try:
            resp = self.client.table("mailboxes").select(
                "id,name,email_address,mailbox_type,connection_config,user_id"
            ).eq("id", mailbox_id).execute()
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.warning(f"Failed to fetch mailbox {mailbox_id}: {e}")
            return None

    def _get_client_mailboxes(self, client_id: str) -> list:
        """Fetch all mailboxes for a client."""
        try:
            resp = self.client.table("mailboxes").select(
                "id,name,email_address,mailbox_type,connection_config,user_id"
            ).eq("client_id", client_id).execute()
            return resp.data or []
        except Exception as e:
            logger.warning(f"Failed to fetch mailboxes for client {client_id}: {e}")
            return []


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_service: Optional[EmailRulesService] = None


def init_email_rules_service(supabase_client) -> EmailRulesService:
    """Initialize the global email rules service."""
    global _service
    _service = EmailRulesService(supabase_client)
    return _service


def get_email_rules_service() -> Optional[EmailRulesService]:
    """Get the initialized email rules service."""
    return _service

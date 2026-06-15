"""Read-only — call the PRODUCTION am_structural_metrics RPC (what the coaching service serves)
for the 4 AMs over the trailing-12-mo window; print the responsiveness block."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from dotenv import load_dotenv
from supabase import create_client
BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
load_dotenv(os.path.join(BACKEND, ".env.production"))
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
CARBON8 = "241d7b99-f099-4557-96e5-212c4af10812"
START, END = "2025-06-16T00:00:00+00:00", "2026-06-16T00:00:00+00:00"
AMS = {"Nic":"5f3afeb3-a5f7-44b8-b657-ec972c92911d","Linda":"e1abc287-805b-4cee-8f95-0b47e1cd8f99",
       "Kenneth":"1332eba5-9121-4b55-91db-a37dd81d5d85","Ehab":"92eba92f-b6be-4fbf-8c49-9f3b7c72ea74"}
WAS = {"Nic":0.297,"Linda":0.099,"Kenneth":0.094,"Ehab":0.038}
print(f"{'AM':<9}{'was_medRAW_h':>14}{'now_medRAW_h':>14}{'now_min':>9}{'reply_rows':>12}{'cov%inb':>9}")
print("-"*70)
for nm,mid in AMS.items():
    d = sb.rpc("am_structural_metrics", {"p_mailbox_id":mid,"p_client_id":CARBON8,
               "p_start":START,"p_end":END}).execute().data
    r = d["responsiveness"]
    mh = r["median_raw_hours"]
    print(f"{nm:<9}{WAS[nm]:>14.3f}{mh:>14.3f}{mh*60:>8.1f}m{r['reply_rows']:>12,}{(r.get('coverage_pct_of_inbound') or 0):>8.1f}%")

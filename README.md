# Comarch API

Python 3.10+ recommended.

Install: `python -m pip install -r requirements.txt`

Run: `python -m streamlit run app.py`

Enter the HTTPS base URL, ProgramCode and already encoded Basic credential. Get Token is optional; every profile lookup obtains its own token. Paste one identifier per line (optional identifier.no header). All nested customer identifiers are exported, including multiple identifiers per response. Duplicate input lines are processed separately. Requests are sequential; no automatic retries. Optional Cookie is sent only to profile searches. HTTP redirects are not followed to avoid forwarding credentials unexpectedly. Credentials and results are held in the running session, not written to disk by the app. Use a trusted local environment for customer data.

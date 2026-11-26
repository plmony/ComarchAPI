import csv
import io
from urllib.parse import urlsplit

import requests
import streamlit as st

COLUMNS = ['accountId', 'customerId', 'identifierNo', 'identifierStatus']
TIMEOUT = (10, 60)
st.set_page_config(page_title='Comarch API', page_icon='🔗', layout='wide')


def get_token(session, url, program_code, client_secret):
    response = session.post(
        f'{url}/oauth/token',
        params={'grant_type': 'client_credentials', 'scope': 'any', 'program_code': program_code},
        headers={'Authorization': f'Basic {client_secret}'},
        timeout=TIMEOUT, allow_redirects=False,
    )
    if response.status_code != 200:
        raise ValueError(f'Token request: HTTP {response.status_code}')
    token = response.json().get('access_token')
    if not isinstance(token, str) or not token:
        raise ValueError('Missing access_token in token response')
    st.session_state.access_token = token
    return token


def search_customer(session, url, identifier, token):
    response = session.get(
        f'{url}/b2b/profile/search',
        params={'identifier.no': identifier},
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'},
        timeout=TIMEOUT, allow_redirects=False,
    )
    if response.status_code != 200:
        raise ValueError(f'Profile search: HTTP {response.status_code}')
    return response.json()


def extract_rows(payload):
    if not isinstance(payload, list):
        raise ValueError('Expected a JSON array in profile response')
    rows = []
    for account in payload:
        for customer in account.get('customers', []):
            for identifier in customer.get('identifiers', []):
                rows.append({
                    'accountId': customer.get('accountId'),
                    'customerId': identifier.get('customerId'),
                    'identifierNo': identifier.get('identifierNo'),
                    'identifierStatus': identifier.get('statusName'),
                })
    return rows


def csv_bytes(rows, columns):
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=columns, delimiter=';', lineterminator='\r\n')
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode('utf-8-sig')


def safe_error(exc):
    if isinstance(exc, requests.Timeout):
        return 'Request timed out'
    if isinstance(exc, requests.RequestException):
        return 'Network or HTTP request error'
    if isinstance(exc, ValueError) and str(exc).startswith(('Token request:', 'Profile search:', 'Missing access_token', 'Expected a JSON array')):
        return str(exc)
    return 'Unexpected or invalid API response'


st.title('Comarch API')
st.caption('Bulk customer identifier extraction')
with st.sidebar:
    st.header('API configuration')
    url = st.text_input('URL', placeholder='https://your-comarch-host').strip().rstrip('/')
    program_code = st.text_input('ProgramCode').strip()
    client_secret = st.text_input('CLIENT_SECRET', type='password', help='Enter the encoded Basic credential, without the Basic prefix.').strip()
    if client_secret.lower().startswith('basic '):
        client_secret = client_secret[6:].strip()
    cookie = st.text_input('Cookie (optional)', type='password', help='Only supply if your Comarch gateway requires a cookie.')
    try:
        parsed = urlsplit(url)
        ready = bool(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment and program_code and client_secret)
    except ValueError:
        ready = False
    if not ready:
        st.caption('Enter an HTTPS base URL and both credentials.')
    if st.button('Get Token', disabled=not ready, use_container_width=True):
        st.session_state.pop('access_token', None)
        try:
            with requests.Session() as session:
                get_token(session, url, program_code, client_secret)
            st.success('Authentication successful')
        except Exception as exc:
            st.error(safe_error(exc))
    if st.button('Clear session data', use_container_width=True):
        st.session_state.clear()
        st.rerun()

st.subheader('Customer identifiers')
raw = st.text_area('Paste one identifier.no per line', height=320, placeholder='FR00136885\nFR00136886\nFR00136887')
ids = [line.strip().lstrip('\ufeff').strip() for line in raw.splitlines() if line.strip()]
if ids and ids[0].lower() in ('identifier.no', 'identifierno'):
    ids.pop(0)
ids = [i for i in ids if i]
st.caption(f'{len(ids):,} identifiers · {2*len(ids):,} planned HTTP requests')
if st.button('Run customer search', type='primary', disabled=not (ready and ids)):
    st.session_state.pop('access_token', None)
    st.session_state.results = []
    st.session_state.errors = []
    st.session_state.found = 0
    st.session_state.not_found = 0
    st.session_state.total = len(ids)
    progress = st.progress(0, text='Starting extraction…')
    status = st.empty()
    with requests.Session() as session:
        for index, identifier in enumerate(ids, 1):
            stage = 'Authentication'
            try:
                token = get_token(session, url, program_code, client_secret)
                stage = 'Profile search'
                # Optional cookie applies only to the profile endpoint.
                if cookie:
                    session.headers['Cookie'] = cookie
                try:
                    payload = search_customer(session, url, identifier, token)
                finally:
                    session.headers.pop('Cookie', None)
                stage = 'Extraction'
                rows = extract_rows(payload)
                st.session_state.results.extend(rows)
                if rows:
                    st.session_state.found += 1
                else:
                    st.session_state.not_found += 1
                    st.session_state.errors.append({'identifierNo': identifier, 'stage': stage, 'error': 'No customer identifiers returned'})
            except Exception as exc:
                st.session_state.errors.append({'identifierNo': identifier, 'stage': stage, 'error': safe_error(exc)})
            progress.progress(index / len(ids), text=f'Processed {index:,} / {len(ids):,}')
            status.caption(f"Found: {st.session_state.found:,} · Rows: {len(st.session_state.results):,} · Issues: {len(st.session_state.errors):,}")
    st.success('Extraction completed. Review the results and any issues below.')

if 'results' in st.session_state:
    rows = st.session_state.results
    errors = st.session_state.errors
    a, b, c, d = st.columns(4)
    a.metric('Successful searches', st.session_state.found)
    b.metric('No results', st.session_state.not_found)
    c.metric('Failed searches', len(errors) - st.session_state.not_found)
    d.metric('Export rows', len(rows))
    st.subheader('Consolidated results')
    st.dataframe(rows, column_order=COLUMNS, use_container_width=True, hide_index=True)
    st.download_button('Download consolidated CSV', csv_bytes(rows, COLUMNS), 'comarch_customers.csv', 'text/csv')
    if errors:
        st.subheader('Failed or empty searches')
        st.dataframe(errors, use_container_width=True, hide_index=True)
        st.download_button('Download issues CSV', csv_bytes(errors, ['identifierNo', 'stage', 'error']), 'comarch_issues.csv', 'text/csv')

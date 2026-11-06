"""End-to-end REST coverage against a running server (http://localhost:7878).

Expectations mirror the original ASP.NET Core controllers: every create
endpoint answers ``200`` with an *empty* body (``Ok()``), so ids are read back
from the listing endpoints.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:7878"
FAILURES: list[str] = []

# A system-wide HTTP proxy (Windows Internet Settings) would otherwise swallow
# loopback requests and answer with an empty 404. Local traffic must bypass it.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    try:
        with OPENER.open(request) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def jget(path, token=None):
    status, text = call("GET", path, None, token)
    try:
        return status, json.loads(text)
    except Exception:
        return status, text


def check(label, status, wanted, extra=None):
    ok = status == wanted
    print(("  ok  " if ok else "  FAIL"), f"{label}: {status} (want {wanted})")
    if not ok:
        FAILURES.append(f"{label}: got {status}, want {wanted} :: {str(extra)[:220]}")


def find(items, key, value):
    for item in items:
        if item.get(key) == value:
            return item
    return None


def main() -> int:
    status, text = call("POST", "/api/v1/auth/login", {"username": "root", "password": "root"})
    check("login", status, 200, text)
    tokens = json.loads(text)
    for key in ("accessToken", "refreshToken", "expiresIn", "tokenType"):
        if key not in tokens:
            FAILURES.append(f"login response missing {key}")
    token = tokens["accessToken"]

    check("refresh", call("POST", "/api/v1/auth/refresh", {"refreshToken": tokens["refreshToken"]})[0], 200)
    check("current user", call("GET", "/api/v1/users/current", None, token)[0], 200)
    check("unauthenticated 401", call("GET", "/api/v1/users/current")[0], 401)

    # --- profile groups -------------------------------------------------
    status, body = jget("/api/v1/profiles/groups", token)
    check("groups list", status, 200, body)
    default_group = body["items"][0]["id"]
    check("delete default group", call("DELETE", f"/api/v1/profiles/groups/{default_group}", None, token)[0], 400)
    check("group create", call("PUT", "/api/v1/profiles/groups", {"name": "临时组", "description": "d", "colorHex": "#112233"}, token)[0], 200)
    status, body = jget("/api/v1/profiles/groups", token)
    created_group = find(body["items"], "name", "临时组")
    if created_group is None:
        FAILURES.append("created profile group not listed")
    else:
        check("group update", call("PUT", f"/api/v1/profiles/groups/{created_group['id']}",
                                   {"id": created_group["id"], "name": "临时组2", "description": "d", "colorHex": "#112233"}, token)[0], 200)
        check("group delete", call("DELETE", f"/api/v1/profiles/groups/{created_group['id']}", None, token)[0], 200)

    # --- subjects -------------------------------------------------------
    subject = {"name": "数学", "initial": "数", "isOutDoor": False, "attachedObjects": {"k": "v"}}
    check("subject create", call("PUT", "/api/v1/profiles/subjects", subject, token)[0], 200)
    status, body = jget("/api/v1/profiles/subjects?pageSize=200", token)
    item = find(body["items"], "name", "数学")
    if item is None:
        FAILURES.append("created subject not listed")
        subject_id = None
    else:
        subject_id = item["id"]
        check("subject get", call("GET", f"/api/v1/profiles/subjects/{subject_id}", None, token)[0], 200)
        check("subject update", call("PUT", f"/api/v1/profiles/subjects/{subject_id}",
                                     {"id": subject_id, "name": "数学2", "initial": "数", "groupId": default_group}, token)[0], 200)
    check("subject update missing", call("PUT", "/api/v1/profiles/subjects/22222222-2222-2222-2222-222222222222", subject, token)[0], 404)

    # --- time layouts ---------------------------------------------------
    layout = {
        "name": "工作日",
        "layouts": [
            {"startSecond": "2026-10-30T08:00:00", "endSecond": "2026-10-30T08:45:00",
             "timeType": 0, "isHideDefault": False, "defaultClassId": "", "attachedObjects": {}},
            {"startSecond": "2026-10-30T08:45:00", "endSecond": "2026-10-30T09:00:00",
             "timeType": 1, "isHideDefault": True, "defaultClassId": "", "attachedObjects": {}},
        ],
        "attachedObjects": {}, "groupId": default_group,
    }
    check("timelayout create", call("PUT", "/api/v1/profiles/timeLayouts", layout, token)[0], 200)
    status, body = jget("/api/v1/profiles/timeLayouts?pageSize=200", token)
    item = find(body["items"], "name", "工作日")
    layout_id = item["id"] if item else None
    if layout_id is None:
        FAILURES.append("created time layout not listed")
    else:
        status, detail = jget(f"/api/v1/profiles/timeLayouts/{layout_id}", token)
        check("timelayout get", status, 200, detail)
        if status == 200:
            n = len(detail.get("layouts", []))
            print("       layouts:", n, "| first start:", detail["layouts"][0]["startSecond"] if n else None)
            if n != 2:
                FAILURES.append(f"timelayout expected 2 items, got {n}")

    # --- class plans ----------------------------------------------------
    if layout_id and subject_id:
        plan = {
            "name": "周一课表",
            "timeRule": {"weekDay": 1, "weekCountDiv": 0, "weekCountDivTotal": 2},
            "timeLayoutId": layout_id,
            "classes": [{"subjectId": subject_id}, {"subjectId": subject_id}],
            "attachedObjects": {}, "isEnabled": True, "groupId": default_group,
        }
        check("classplan create", call("PUT", "/api/v1/profiles/classPlans", plan, token)[0], 200)
        status, body = jget("/api/v1/profiles/classPlans?pageSize=200", token)
        item = find(body["items"], "name", "周一课表")
        plan_id = item["id"] if item else None
        if plan_id is None:
            FAILURES.append("created class plan not listed")
        else:
            status, detail = jget(f"/api/v1/profiles/classPlans/{plan_id}", token)
            check("classplan get", status, 200, detail)
            if status == 200:
                print("       classPlan keys:", sorted(detail.get("classPlan", {}).keys()))
                print("       classNames:", detail.get("classNames"))
                if "classNames" not in detail or len(detail["classNames"]) != 2:
                    FAILURES.append(f"classNames wrong: {detail.get('classNames')}")
                if detail.get("classPlan", {}).get("timeLayoutId") != layout_id:
                    FAILURES.append("classPlan.timeLayoutId mismatch")
            check("delete layout in use", call("DELETE", f"/api/v1/profiles/timeLayouts/{layout_id}", None, token)[0], 400)
    else:
        plan_id = None

    # --- policies -------------------------------------------------------
    policy = {"name": "策略A", "isEnabled": True, "content": {"disableDebugMenu": True}, "groupId": default_group}
    check("policy create", call("POST", "/api/v1/policies", policy, token)[0], 200)
    status, body = jget("/api/v1/policies?pageSize=200", token)
    item = find(body["items"], "name", "策略A")
    policy_id = item["id"] if item else None
    if policy_id:
        check("policy get", call("GET", f"/api/v1/policies/{policy_id}", None, token)[0], 200)
        check("policy delete", call("DELETE", f"/api/v1/policies/{policy_id}", None, token)[0], 200)
        check("policy delete missing", call("DELETE", f"/api/v1/policies/{policy_id}", None, token)[0], 404)

    # --- default settings ----------------------------------------------
    setting = {"name": "默认设置", "description": "d", "settings": {"a": 1}}
    check("setting create", call("POST", "/api/v1/default-settings", setting, token)[0], 200)
    status, body = jget("/api/v1/default-settings", token)
    item = find(body, "name", "默认设置")
    setting_id = item["id"] if item else None
    if setting_id:
        check("setting get", call("GET", f"/api/v1/default-settings/{setting_id}", None, token)[0], 200)
        check("setting update", call("POST", f"/api/v1/default-settings/{setting_id}", setting, token)[0], 200)
        check("setting delete", call("DELETE", f"/api/v1/default-settings/{setting_id}", None, token)[0], 200)

    # --- assignees ------------------------------------------------------
    status, clients = jget("/api/v1/clients_registry/all", token)
    cuid = clients["items"][0]["cuid"] if status == 200 and clients["items"] else None
    if cuid and subject_id:
        assignee = {"objectId": subject_id, "objectType": 3, "assigneeType": 1,
                    "targetClientCuid": cuid, "targetClientId": None, "targetGroupId": None}
        check("assignee create", call("POST", "/api/v1/assignees/all", assignee, token)[0], 200)
        status, listing = jget(f"/api/v1/assignees/by-object/assignees/3/{subject_id}", token)
        check("assignee list by object", status, 200, listing)
        if status == 200 and listing["items"]:
            aid = listing["items"][0]["id"]
            check("assignee delete", call("DELETE", f"/api/v1/assignees/all/{aid}", None, token)[0], 200)
        for kind in ("clients", "clients-abstract", "client-groups"):
            check(f"assignee by-object {kind}", call("GET", f"/api/v1/assignees/by-object/{kind}/3/{subject_id}", None, token)[0], 200)

    # --- clients --------------------------------------------------------
    if cuid:
        check("client query", call("GET", f"/api/v1/clients_registry/query/{cuid}", None, token)[0], 200)
    check("client query missing", call("GET", "/api/v1/clients_registry/query/11111111-1111-1111-1111-111111111111", None, token)[0], 400)
    check("client unregister missing", call("DELETE", "/api/v1/clients_registry/unregister?Cuid=11111111-1111-1111-1111-111111111111", None, token)[0], 400)

    # --- client groups --------------------------------------------------
    check("client group list", call("GET", "/api/v1/client_groups", None, token)[0], 200)
    check("client group get", call("GET", "/api/v1/client_groups/1", None, token)[0], 200)
    check("client group get missing", call("GET", "/api/v1/client_groups/999999", None, token)[0], 404)
    check("client group create", call("PUT", "/api/v1/client_groups", {"name": "新组", "colorHex": "#00ff00"}, token)[0], 200)
    status, body = jget("/api/v1/client_groups?pageSize=100", token)
    cg = find(body["items"], "name", "新组")
    if cg:
        check("client group delete", call("DELETE", f"/api/v1/client_groups/{cg['id']}", None, token)[0], 200)
    check("delete default client group", call("DELETE", "/api/v1/client_groups/1", None, token)[0], 400)
    check("delete global client group", call("DELETE", "/api/v1/client_groups/-1", None, token)[0], 400)

    # --- organization settings -----------------------------------------
    brand = {"organizationName": "测试学校", "logoUrl": "http://x/logo.png",
             "customLoginBanner": None, "loginFormPlacement": "right"}
    check("brand post", call("POST", "/api/v1/settings/brand", brand, token)[0], 200)
    status, body = jget("/api/v1/settings/brand")
    check("brand get", status, 200, body)
    if status == 200 and body.get("organizationName") != "测试学校":
        FAILURES.append(f"brand roundtrip failed: {body}")

    basic = {"allowUnregisteredClients": True, "allowPublicRegister": False,
             "customPublicRootUrl": "", "customPublicApiUrl": "", "customPublicGrpcUrl": ""}
    check("basic post", call("POST", "/api/v1/settings/basic", basic, token)[0], 200)
    status, body = jget("/api/v1/settings/basic", token)
    check("basic get", status, 200, body)
    if status == 200 and body.get("allowUnregisteredClients") is not True:
        FAILURES.append(f"basic roundtrip failed: {body}")
    check("complete-oobe", call("POST", "/api/v1/settings/complete-oobe", None, token)[0], 200)

    # --- users ----------------------------------------------------------
    check("user create", call("POST", "/api/v1/users/create",
                              {"user": {"userName": "tester", "name": "测试员"}, "password": "Passw0rd!"}, token)[0], 200)
    status, body = jget("/api/v1/users/all?pageIndex=1&pageSize=50", token)
    check("users list", status, 200, body)
    tester = find(body["items"], "userName", "tester")
    if tester:
        uid = tester["id"]
        check("user create dup", call("POST", "/api/v1/users/create",
                                      {"user": {"userName": "tester", "name": "测试员"}, "password": "Passw0rd!"}, token)[0], 400)
        check("user update", call("POST", f"/api/v1/users/{uid}",
                                  {"userName": "tester", "name": "改名", "roles": ["UsersManager"]}, token)[0], 200)
        check("user set password", call("POST", f"/api/v1/users/{uid}/set-password", {"newPassword": "NewPass1!"}, token)[0], 200)
        check("user delete", call("DELETE", f"/api/v1/users/{uid}", None, token)[0], 200)
        check("user delete missing", call("DELETE", f"/api/v1/users/{uid}", None, token)[0], 404)
    check("delete root", call("DELETE", "/api/v1/users/00000000-0000-0000-0000-000000000000", None, token)[0], 404)

    # --- profile upload & teardown -------------------------------------
    upload = {"subjects": {"33333333-3333-3333-3333-333333333333": {"name": "英语", "initial": "英"}},
              "timeLayouts": {}, "classPlans": {}}
    check("profile upload", call("POST", "/api/v1/profiles/upload?replace=false", upload, token)[0], 200)
    check("uploaded subject", call("GET", "/api/v1/profiles/subjects/33333333-3333-3333-3333-333333333333", None, token)[0], 200)
    check("uploaded subject delete", call("DELETE", "/api/v1/profiles/subjects/33333333-3333-3333-3333-333333333333", None, token)[0], 200)

    if plan_id:
        check("classplan delete", call("DELETE", f"/api/v1/profiles/classPlans/{plan_id}", None, token)[0], 200)
    if layout_id:
        check("timelayout delete", call("DELETE", f"/api/v1/profiles/timeLayouts/{layout_id}", None, token)[0], 200)
    if subject_id:
        check("subject delete", call("DELETE", f"/api/v1/profiles/subjects/{subject_id}", None, token)[0], 200)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S):")
        for item in FAILURES:
            print(" -", item)
        return 1
    print("ALL REST CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

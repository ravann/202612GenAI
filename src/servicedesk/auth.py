"""Identity: three static dev tokens, each mapped to a user, a role and scopes.

There is no login, OAuth or identity provider in this course (Session 8 discusses
what those would add). A real service would get the same three facts (who, which
role, which scopes) from a validated token issued by the identity provider.
"""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from errors import ServiceError
from faults import FAULTS


class User:
    def __init__(self, username, role, scopes):
        self.username = username
        self.role = role
        self.scopes = scopes

    def has_scope(self, scope):
        return scope in self.scopes


USERS_BY_TOKEN = {
    "dev-requester-token": User("alice", "requester",
                                ["incidents:read", "runbooks:read"]),
    "dev-engineer-token": User("bob", "engineer",
                               ["incidents:read", "incidents:write", "changes:write", "runbooks:read"]),
    "dev-change-manager-token": User("carol", "change-manager",
                                     ["incidents:read", "incidents:write", "changes:write", "changes:approve",
                                      "runbooks:read", "runbooks:restricted"]),
}

# Reads "Authorization: Bearer <token>" and documents the scheme in /openapi.json.
# auto_error=False: we send our own 401 body instead of FastAPI's default.
bearer_scheme = HTTPBearer(auto_error=False,
                           description="Send one of the dev tokens: Authorization: Bearer <token>.")


def check_token(credentials):
    if credentials is None:
        raise ServiceError(401, "unauthorized", "Missing bearer token",
                           "Send the header Authorization: Bearer <token>; the dev tokens are in src/servicedesk/README.md",
                           headers={"WWW-Authenticate": "Bearer"})
    user = USERS_BY_TOKEN.get(credentials.credentials)
    if user is None:
        raise ServiceError(401, "unauthorized", "Unknown bearer token",
                           "Use one of the three dev tokens listed in src/servicedesk/README.md",
                           headers={"WWW-Authenticate": "Bearer"})
    return user


# FastAPI runs a function given to Depends() before the endpoint and passes its result in.
def get_caller(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
    """Used by every normal API endpoint: apply any injected fault, then check the token."""
    FAULTS.apply()
    return check_token(credentials)


def get_admin_caller(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
    """Used by the /_admin endpoints: check the token, never inject a fault."""
    return check_token(credentials)


def require_scope(user, scope):
    if not user.has_scope(scope):
        raise ServiceError(403, "forbidden",
                           f"User {user.username} (role {user.role}) lacks the scope {scope}",
                           f"This operation needs the scope {scope}; see the token table in src/servicedesk/README.md")


def require_role(user, role):
    if user.role != role:
        raise ServiceError(403, "forbidden",
                           f"User {user.username} has the role {user.role}; only the {role} role may do this",
                           f"Ask a user with the {role} role")

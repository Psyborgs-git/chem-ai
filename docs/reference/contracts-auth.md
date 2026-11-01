# Session and owner setup API — JSON contract details

These excerpts are generated from the implementation without importing it. They specify accepted fields, conditional validation, defaults and response construction for flexible JSON interfaces. They complement the endpoint prose; implementation expressions refer to the named source service rather than a live execution.

## LoginRequest

Source: `services/studio-api/src/studio/api/auth_routes.py:LoginRequest`.

```python
class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1)
```

## SetupRequest

Source: `services/studio-api/src/studio/api/auth_routes.py:SetupRequest`.

```python
class SetupRequest(BaseModel):
    login: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=10)
```

## login

Source: `services/studio-api/src/studio/api/auth_routes.py:login`.

```python
@auth_router.post("/login")
def login(
    body: LoginRequest, request: Request, response: Response, db: DbSession
) -> dict[str, Any]:
    settings = request.app.state.settings
    ws = _default_workspace(db)
    principal = authenticate_password(db, ws.id, body.login, body.password)
    issued = issue_session(db, ws.id, principal, settings.session_ttl_seconds)
    db.commit()
    _set_cookie(response, issued.token, issued.expires_at)
    return {"status": "authenticated", "expiresAt": issued.expires_at}
```

## logout

Source: `services/studio-api/src/studio/api/auth_routes.py:logout`.

```python
@auth_router.post("/logout")
def logout(request: Request, response: Response, db: DbSession) -> dict[str, Any]:
    ctx = build_context(request, db)
    if ctx.auth_session_id is not None:
        revoke_session(db, ctx.workspace_id, ctx.auth_session_id)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "logged_out"}
```

## setup_needed

Source: `services/studio-api/src/studio/api/auth_routes.py:setup_needed`.

```python
@auth_router.get("/setup-needed")
def setup_needed(request: Request, db: DbSession) -> dict[str, Any]:
    ws = db.execute(select(Workspace).order_by(Workspace.created_at).limit(1)).scalar_one_or_none()
    needed = ws is None or not workspace_has_owner(db, ws.id)
    return {"setupNeeded": needed}
```

## setup_owner

Source: `services/studio-api/src/studio/api/auth_routes.py:setup_owner`.

```python
@auth_router.post("/setup")
def setup_owner(
    body: SetupRequest, request: Request, response: Response, db: DbSession
) -> dict[str, Any]:
    settings = request.app.state.settings
    ws = _default_workspace(db)
    if workspace_has_owner(db, ws.id):
        raise DomainError(ErrorCode.CONFLICT, "owner already configured")
    principal = create_owner(db, ws, body.login, body.display_name, body.password)
    issued = issue_session(db, ws.id, principal, settings.session_ttl_seconds)
    db.commit()
    _set_cookie(response, issued.token, issued.expires_at)
    return {"status": "owner_configured", "expiresAt": issued.expires_at}
```

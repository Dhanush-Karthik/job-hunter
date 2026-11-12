from fastapi import HTTPException


def todo() -> HTTPException:
    """Placeholder until Wave 2 implements the route. Shape is fixed by the contract."""
    return HTTPException(status_code=501, detail="not implemented yet")

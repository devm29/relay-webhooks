from anyio import to_thread
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# argon2 is deliberately slow (tens of milliseconds); keep it off the event loop.
async def hash_password_async(password: str) -> str:
    return await to_thread.run_sync(hash_password, password)


async def verify_password_async(password_hash: str, password: str) -> bool:
    return await to_thread.run_sync(verify_password, password_hash, password)

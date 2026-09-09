import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app._database.models import AccountModel, TransactionModel, UserModel
from app.Finances.schemas.account import DEFAULT_ACCOUNTS, AccountCreate, AccountUpdate


def seed_default_accounts(db: Session, user_id: uuid.UUID) -> list[AccountModel]:
    """Give a new account holder the four pots from the project notes.

    Done lazily on first read rather than at signup, so accounts that already
    existed before this module get them too.
    """
    created = [
        AccountModel(
            id=uuid.uuid4(),
            user_id=user_id,
            name=name,
            kind=kind.value,
            income_share=share,
            position=index,
        )
        for index, (name, kind, share) in enumerate(DEFAULT_ACCOUNTS)
    ]
    db.add_all(created)
    db.commit()
    for account in created:
        db.refresh(account)
    return created


def balances_by_account(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, float]:
    """Every account's balance in one grouped query, not one query per account."""
    rows = (
        db.query(TransactionModel.account_id, func.sum(TransactionModel.amount))
        .filter(TransactionModel.user_id == user_id)
        .group_by(TransactionModel.account_id)
        .all()
    )
    return {account_id: round(total or 0.0, 2) for account_id, total in rows}


def attach_balances(accounts: list[AccountModel], balances: dict[uuid.UUID, float]):
    for account in accounts:
        account.balance = balances.get(account.id, 0.0)
    return accounts


def get_accounts(db: Session, user_id: uuid.UUID, include_archived: bool = False):
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    accounts = db.query(AccountModel).filter(AccountModel.user_id == user_id).all()
    if not accounts:
        accounts = seed_default_accounts(db, user_id)

    if not include_archived:
        accounts = [account for account in accounts if not account.archived]

    accounts.sort(key=lambda account: (account.position, account.name))
    return attach_balances(accounts, balances_by_account(db, user_id))


def get_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID):
    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == user_id)
        .first()
    )
    if account is None:
        return None

    return attach_balances([account], balances_by_account(db, user_id))[0]


def create_account(db: Session, user_id: uuid.UUID, data: AccountCreate):
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None

    existing = (
        db.query(AccountModel)
        .filter(AccountModel.user_id == user_id, AccountModel.name.ilike(data.name))
        .first()
    )
    if existing:
        raise ValueError("An account with that name already exists")

    account = AccountModel(
        id=uuid.uuid4(),
        user_id=user_id,
        name=data.name,
        kind=data.kind.value,
        income_share=data.income_share,
        archived=data.archived,
        position=data.position,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    account.balance = 0.0
    return account


def update_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID, data: AccountUpdate):
    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == user_id)
        .first()
    )
    if account is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "kind" in update_data and update_data["kind"] is not None:
        kind = update_data["kind"]
        update_data["kind"] = kind.value if hasattr(kind, "value") else kind

    new_name = update_data.get("name")
    if new_name is not None:
        clash = (
            db.query(AccountModel)
            .filter(
                AccountModel.user_id == user_id,
                AccountModel.id != account_id,
                AccountModel.name.ilike(new_name),
            )
            .first()
        )
        if clash:
            raise ValueError("An account with that name already exists")

    for key, value in update_data.items():
        setattr(account, key, value)

    db.commit()
    db.refresh(account)
    return attach_balances([account], balances_by_account(db, user_id))[0]


def delete_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID):
    """Refuses while the account still holds history.

    Deleting would cascade its transactions away, silently changing balances
    elsewhere if any were transfer halves. Archiving is the safe route.
    """
    account = (
        db.query(AccountModel)
        .filter(AccountModel.id == account_id, AccountModel.user_id == user_id)
        .first()
    )
    if account is None:
        return None

    count = (
        db.query(func.count(TransactionModel.id))
        .filter(TransactionModel.account_id == account_id)
        .scalar()
    )
    if count:
        raise ValueError(
            f"{account.name} has {count} transactions. Archive it instead of deleting."
        )

    db.delete(account)
    db.commit()
    return account

from fastapi import APIRouter, Depends

from . import operations
from .auth import current_user, require
from .contracts import Role
from .operations_input import ActionNote, ClosureIn, DiversionIn, SettlementIn

router = APIRouter(prefix='/operations')
operator = require(Role.OPERATOR)
analyst = require(Role.ANALYST)
supervisor = require(Role.SUPERVISOR)
closure_canceller = require(Role.OPERATOR, Role.SUPERVISOR)


@router.get('/closures')
def list_closures(user=Depends(current_user)):
    return operations.closures()


@router.post('/closures', status_code=201)
def propose_closure(item: ClosureIn, user=Depends(operator)):
    return operations.propose_closure(item, user['email'])


@router.post('/closures/{closure_id}/approve')
def approve_closure(closure_id: int, item: ActionNote, user=Depends(supervisor)):
    return operations.change_closure(closure_id, user['email'], user['role'], 'approve', item.note)


@router.post('/closures/{closure_id}/cancel')
def cancel_closure(closure_id: int, item: ActionNote, user=Depends(closure_canceller)):
    return operations.change_closure(closure_id, user['email'], user['role'], 'cancel', item.note)


@router.get('/diversions')
def list_diversions(user=Depends(current_user)):
    return operations.diversions()


@router.post('/diversions', status_code=201)
def propose_diversion(item: DiversionIn, user=Depends(operator)):
    return operations.propose_diversion(item, user['email'])


@router.post('/diversions/{diversion_id}/activate')
def activate_diversion(diversion_id: int, item: ActionNote, user=Depends(operator)):
    return operations.change_diversion(diversion_id, user['email'], 'activate', item.note)


@router.post('/diversions/{diversion_id}/cancel')
def cancel_diversion(diversion_id: int, item: ActionNote, user=Depends(operator)):
    return operations.change_diversion(diversion_id, user['email'], 'cancel', item.note)


@router.get('/settlements')
def list_settlements(user=Depends(current_user)):
    return operations.settlements()


@router.post('/settlements')
def submit_settlement(item: SettlementIn, user=Depends(analyst)):
    return operations.submit_settlement(item, user['email'])


@router.post('/settlements/{settlement_id}/return')
def return_settlement(settlement_id: int, item: ActionNote, user=Depends(supervisor)):
    return operations.review_settlement(settlement_id, user['email'], 'return', item.note)


@router.post('/settlements/{settlement_id}/accept')
def accept_settlement(settlement_id: int, item: ActionNote, user=Depends(supervisor)):
    return operations.review_settlement(settlement_id, user['email'], 'accept', item.note)

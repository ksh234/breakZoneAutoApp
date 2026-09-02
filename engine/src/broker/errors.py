"""브로커 예외 계층. 호출측(전략)은 이 타입들만 알면 된다."""
from __future__ import annotations


class BrokerError(Exception):
    """모든 브로커 오류의 최상위."""


class AuthError(BrokerError):
    """인증/토큰 실패 (401, 토큰 발급 실패 등)."""


class OrderRejected(BrokerError):
    """주문 거부 (증거금 부족·가격 오류·장 상태 등). 재시도 금지."""


class RateLimited(BrokerError):
    """호출한도 초과 (429). 백오프 후 재시도 가능."""


class TransientError(BrokerError):
    """일시적 오류 (네트워크·5xx). 백오프 후 재시도 가능."""

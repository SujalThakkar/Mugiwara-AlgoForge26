"""
api/services/minting_service.py — Backend-controlled SBT minting via web3.py v6.

Calls GoalBadgeSBT.mintBadge() or batchMintBadge() from the backend
verifier wallet. Used after a goal is completed and IPFS metadata is ready.
"""

import os
import logging
from typing import Any

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
AMOY_RPC_URL         = os.getenv("AMOY_RPC_URL", "https://rpc-amoy.polygon.technology")
VERIFIER_PRIVATE_KEY = os.getenv("VERIFIER_PRIVATE_KEY", "")
SBT_CONTRACT_ADDRESS = os.getenv("SBT_CONTRACT_ADDRESS", "")

# Minimal ABI — only the functions we call from backend
SBT_ABI: list[dict[str, Any]] = [
    {
        "inputs": [
            {"internalType": "address", "name": "recipient", "type": "address"},
            {"internalType": "string",  "name": "goalTitle", "type": "string"},
            {"internalType": "string",  "name": "tokenUri",  "type": "string"},
        ],
        "name": "mintBadge",
        "outputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address[]", "name": "recipients", "type": "address[]"},
            {"internalType": "string",    "name": "goalTitle",  "type": "string"},
            {"internalType": "string",    "name": "tokenUri",   "type": "string"},
        ],
        "name": "batchMintBadge",
        "outputs": [{"internalType": "uint256[]", "name": "tokenIds", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


def _get_w3() -> Web3:
    """Create a Web3 instance with Polygon Amoy POA middleware."""
    w3 = Web3(Web3.HTTPProvider(AMOY_RPC_URL))
    # Polygon uses POA (extra data field > 32 bytes) — inject middleware
    try:
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    except Exception:
        # web3.py v7+ handles this automatically; safe to ignore if it fails
        pass
    return w3


def _get_contract(w3: Web3) -> Any:
    if not SBT_CONTRACT_ADDRESS:
        raise RuntimeError("SBT_CONTRACT_ADDRESS not set in .env")
    return w3.eth.contract(
        address=Web3.to_checksum_address(SBT_CONTRACT_ADDRESS),
        abi=SBT_ABI,
    )


def _build_and_send(w3: Web3, contract: Any, fn_name: str, args: list) -> str:
    """Build, sign, and send a transaction. Returns tx_hash hex string."""
    if not VERIFIER_PRIVATE_KEY:
        raise RuntimeError("VERIFIER_PRIVATE_KEY not set in .env")

    account   = w3.eth.account.from_key(VERIFIER_PRIVATE_KEY)
    nonce     = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price

    # Amoy requires minimum 2.5 gwei; enforce it
    effective_gas_price = max(int(gas_price), w3.to_wei(2.5, "gwei"))

    contract_fn = getattr(contract.functions, fn_name)(*args)
    tx = contract_fn.build_transaction({
        "from":     account.address,
        "nonce":    nonce,
        "gasPrice": effective_gas_price,
        "gas":      300_000,  # safe upper bound for mint
    })

    signed  = w3.eth.account.sign_transaction(tx, VERIFIER_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    logger.info(f"[Mint] tx sent: {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt["status"] != 1:
        raise RuntimeError(f"Transaction reverted: {tx_hash.hex()}")

    logger.info(f"[Mint] confirmed in block {receipt['blockNumber']}")
    return tx_hash.hex()


async def mint_single_badge(
    recipient:  str,
    goal_title: str,
    token_uri:  str,
) -> dict:
    """
    Mint a single SBT badge to a recipient.

    Args:
        recipient:  Wallet address (checksummed or lowercase).
        goal_title: Short label for event log.
        token_uri:  IPFS URI (ipfs://CID).

    Returns:
        {"tx_hash": "0x...", "success": True} or {"success": False, "error": "..."}
    """
    try:
        w3       = _get_w3()
        contract = _get_contract(w3)
        tx_hash  = _build_and_send(
            w3, contract,
            "mintBadge",
            [Web3.to_checksum_address(recipient), goal_title, token_uri],
        )
        return {"tx_hash": tx_hash, "success": True}
    except Exception as e:
        logger.error(f"[Mint] mintBadge failed: {e}")
        return {"success": False, "error": str(e)}


async def batch_mint_badges(
    recipients: list[str],
    goal_title: str,
    token_uri:  str,
) -> dict:
    """
    Batch mint SBT badges to multiple recipients (group goals). Max 20 per call.

    Args:
        recipients: List of wallet addresses (checksummed or lowercase).
        goal_title: Shared goal label.
        token_uri:  Shared IPFS URI.

    Returns:
        {"tx_hash": "0x...", "success": True} or {"success": False, "error": "..."}
    """
    if len(recipients) > 20:
        raise ValueError("batch_mint_badges: max 20 recipients per call")
    try:
        w3        = _get_w3()
        contract  = _get_contract(w3)
        checksums = [Web3.to_checksum_address(r) for r in recipients]
        tx_hash   = _build_and_send(
            w3, contract,
            "batchMintBadge",
            [checksums, goal_title, token_uri],
        )
        return {"tx_hash": tx_hash, "success": True}
    except Exception as e:
        logger.error(f"[Mint] batchMintBadge failed: {e}")
        return {"success": False, "error": str(e)}

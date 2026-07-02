def okx_to_internal(inst_id: str) -> str:
    return inst_id.replace("-USDT-SWAP", "USDT").replace("-", "")


def internal_to_okx(symbol: str) -> str:
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    return f"{base}-USDT-SWAP"


def gate_to_internal(contract: str) -> str:
    return contract.replace("_USDT", "USDT")


def internal_to_gate(symbol: str) -> str:
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    return f"{base}_USDT"


def mexc_to_internal(symbol: str) -> str:
    return symbol.replace("_USDT", "USDT")


def internal_to_mexc(symbol: str) -> str:
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    return f"{base}_USDT"

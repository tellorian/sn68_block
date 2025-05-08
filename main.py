import asyncio
import bittensor as bt
from pydantic import BaseModel
from fastapi import FastAPI
from typing import cast
from types import SimpleNamespace
from bittensor.core.chain_data.utils import decode_metadata
from datasets import load_dataset
import random
from typing import List, Optional

netuid = 68
epoch_length = 361
current_block = None
current_protein = None
current_indices = None

app = FastAPI()
dataset = None

class Response(BaseModel):
    current_block: int
    current_protein: str
    current_indices: Optional[List[int]]

import requests

async def _get_current_block(subtensor):
    global current_block
    current_block = await subtensor.get_current_block()
    return current_block

def get_challenge_proteins_from_blockhash(block_hash: str, num_targets: int, num_antitargets: int) -> dict:
    """
    Use block_hash as a seed to pick 'num_targets' and 'num_antitargets' random entries
    from the 'Metanova/Proteins' dataset. Returns {'targets': [...], 'antitargets': [...]}.
    """
    if not (isinstance(block_hash, str) and block_hash.startswith("0x")):
        raise ValueError("block_hash must start with '0x'.")
    if num_targets < 0 or num_antitargets < 0:
        raise ValueError("num_targets and num_antitargets must be non-negative.")

    # Convert block hash to an integer seed
    try:
        seed = int(block_hash[2:], 16)
    except ValueError:
        raise ValueError(f"Invalid hex in block_hash: {block_hash}")

    # Initialize random number generator
    rng = random.Random(seed)

    dataset_size = len(dataset)
    if dataset_size == 0:
        raise ValueError("Dataset is empty; cannot pick random entries.")

    # Grab all required indices at once, ensure uniqueness
    unique_indices = rng.sample(range(dataset_size), k=(num_targets + num_antitargets))

    # Split the first 'num_targets' for targets, the rest for antitargets
    target_indices = unique_indices[:num_targets]
    antitarget_indices = unique_indices[num_targets:]

    # Convert indices to protein codes
    targets = [dataset[i]["Entry"] for i in unique_indices]

    return targets, unique_indices

async def get_current_block():
    global current_block, epoch_length, current_protein, current_indices
    
    async with bt.async_subtensor(network="local") as subtensor:
        while True:
            await _get_current_block(subtensor)
            if (current_protein is None or current_block % epoch_length == 0):
                epoch_start = (current_block // epoch_length) * epoch_length
                current_block_hash = await subtensor.determine_block_hash(epoch_start)
                challenge_proteins, current_indices = get_challenge_proteins_from_blockhash(current_block_hash, 1, 3)
                current_protein = "|".join(challenge_proteins)
            print(f"current_block: {current_block}, current_protein:{current_protein}")
            await asyncio.sleep(4)

async def main():
    await get_current_block()

@app.get("/", response_model=Response)
async def get_current_data():
    global current_block, current_protein, current_indices
    if current_block is None or current_protein is None:
        raise HTTPException(status_code=500, detail="Not Ready for fetching data")
    return Response(current_block=current_block, current_protein=current_protein, current_indices=current_indices)

@app.on_event("startup")
async def startup_event():
    global dataset
    dataset = load_dataset("Metanova/Proteins", split="train")
    asyncio.create_task(main())
    
import asyncio
import bittensor as bt
from pydantic import BaseModel
from fastapi import FastAPI
from typing import cast
from types import SimpleNamespace
from bittensor.core.chain_data.utils import decode_metadata
from datasets import load_dataset

netuid = 68
epoch_length = 360
current_block = None
current_protein = None

app = FastAPI()

class Response(BaseModel):
    current_block: int
    current_protein: str

import requests

async def _get_current_block(subtensor):
    global current_block
    current_block = await subtensor.get_current_block()
    return current_block

def get_index_in_range_from_blockhash(block_hash: str, range_max: int) -> int:

    block_hash_str = block_hash.lower().removeprefix('0x')
    
    # Convert the hex string to an integer
    hash_int = int(block_hash_str, 16)

        # Modulo by the desired range
    random_index = hash_int % range_max

    return random_index

def get_protein_code_at_index(index: int) -> str:
    
    dataset = load_dataset("Metanova/Proteins", split="train")
    row = dataset[index]  # 0-based indexing
    return row["Entry"]

async def get_current_block():
    global current_block, epoch_length, current_protein
    
    async with bt.async_subtensor(network="local") as subtensor:
        while True:
            await _get_current_block(subtensor)
            if (current_protein is None or current_block % 360 == 0):
                epoch_start = (current_block // epoch_length) * epoch_length
                current_block_hash = await subtensor.determine_block_hash(epoch_start)
                prev_block_hash = await subtensor.determine_block_hash(epoch_start - 1)
                target_random_index = get_index_in_range_from_blockhash(current_block_hash, 179620)
                antitarget_random_index = get_index_in_range_from_blockhash(prev_block_hash, 179620)
                target_protein_code = get_protein_code_at_index(target_random_index)
                antitarget_protein_code = get_protein_code_at_index(antitarget_random_index)
                current_protein = f"{target_protein_code}|{antitarget_protein_code}"
            print(f"current_block: {current_block}, current_protein:{current_protein}")
            await asyncio.sleep(4)

async def main():
    await get_current_block()

@app.get("/", response_model=Response)
async def get_current_data():
    global current_block, current_protein
    if current_block is None or current_protein is None:
        raise HTTPException(status_code=500, detail="Not Ready for fetching data")
    return Response(current_block=current_block, current_protein=current_protein)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(main())
    
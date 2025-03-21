import asyncio
import bittensor as bt
from pydantic import BaseModel
from fastapi import FastAPI
from typing import cast
from types import SimpleNamespace
from bittensor.core.chain_data.utils import decode_metadata

netuid = 68
epoch_length = 360
current_block = None
current_protein = None

app = FastAPI()

class Response(BaseModel):
    current_block: int
    current_protein: str

import requests

def set_repo_visibility(make_private: bool):
    url = f"https://api.github.com/repos/tellorian/sn68_submit"
    github_token = os.getenv("GITHUB_TOKEN")
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    
    payload = {"private": not make_private} 
    
    response = requests.patch(url, json=payload, headers=headers)

    if response.status_code == 200:
        print(f"Repository is now {'private' if not make_private else 'public'}.")
    else:
        print(f"Failed to update repository visibility: {response.status_code}")
        print(response.json())  # Print error details

async def _get_current_block(subtensor):
    global current_block
    current_block = await subtensor.get_current_block()
    return current_block

async def get_commitments(subtensor, metagraph, block_hash):
    global netuid
    commits = await asyncio.gather(*[
        subtensor.substrate.query(
            module="Commitments",
            storage_function="CommitmentOf",
            params=[netuid, hotkey],
            block_hash=block_hash,
        ) for hotkey in metagraph.hotkeys
    ])

    # Process the results and build a dictionary with additional metadata.
    result = {}
    for uid, hotkey in enumerate(metagraph.hotkeys):
        commit = cast(dict, commits[uid])
        if commit:
            result[hotkey] = SimpleNamespace(
                uid=uid,
                hotkey=hotkey,
                block=commit['block'],
                data=decode_metadata(commit)
            )
    return result

async def get_current_block():
    global current_block, epoch_length, current_protein
    
    while True:
        async with bt.async_subtensor(network="local") as subtensor:
            # Initialize and sync metagraph
            metagraph = await subtensor.metagraph(netuid)
            await metagraph.sync()
            await _get_current_block(subtensor)
            # set_repo_visibility(current_block % 360 > 357 or current_block % 360 < 7)
            epoch_start = (current_block // epoch_length) * epoch_length

            block_hash = await subtensor.determine_block_hash(current_block)
            commits = await get_commitments(subtensor, metagraph, block_hash)

            # Filter to keep only commits that occurred after or at epoch start
            fresh_commits = {
                hotkey: commit
                for hotkey, commit in commits.items()
                if commit.block > epoch_start
            }
            if not fresh_commits:
                print(f"No commits found in block window [{epoch_start}, {current_block}].")
                await asyncio.sleep(6)
                continue

            highest_stake_commit = max(
                fresh_commits.values(),
                key=lambda c: metagraph.S[c.uid],
                default=None
            )
            current_protein = highest_stake_commit.data if highest_stake_commit else None
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
    
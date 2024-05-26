#!/usr/bin/env python3

from web3 import Web3
import requests
import json
import logging
import time
import os

# Setup logging
logging.basicConfig(level=logging.INFO)

# Setup Web3 provider
quicknode_url = "[Replace with yours]"
web3 = Web3(Web3.HTTPProvider(quicknode_url))

if web3.is_connected():
    print("Connected to Ethereum mainnet via QuickNode")
else:
    print("Failed to connect to Ethereum mainnet")

# Load the ERC-20 ABI from the JSON file
with open('erc20_abi.json', 'r') as abi_file:
    erc20_abi = json.load(abi_file)

# Load the ERC-721 ABI from the JSON file
with open('erc721_abi.json', 'r') as abi_file:
    erc721_abi = json.load(abi_file)

# Fetch wallet balance
def get_wallet_balance(address):
    balance_wei = web3.eth.get_balance(address)
    balance_eth = web3.from_wei(balance_wei, 'ether')
    return balance_eth

# Fetch ERC-20 token balance
def get_erc20_balance(address, token_address):
    token_address = Web3.to_checksum_address(token_address)
    token_contract = web3.eth.contract(address=token_address, abi=erc20_abi)
    balance = token_contract.functions.balanceOf(address).call()
    return balance

# Fetch ERC-20 token name and symbol
def get_token_name_symbol(token_address):
    token_address = Web3.to_checksum_address(token_address)
    token_contract = web3.eth.contract(address=token_address, abi=erc20_abi)
    try:
        name = token_contract.functions.name().call()
        symbol = token_contract.functions.symbol().call()
    except Exception as e:
        name = 'Unknown'
        symbol = 'Unknown'
        logging.warning(f"Could not fetch name and symbol for {token_address}: {e}")
    return name, symbol

# Fetch transaction history using Etherscan API
def get_transaction_history(address, api_key):
    url = f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&sort=asc&apikey={api_key}"
    response = requests.get(url)
    transactions = response.json().get('result', [])
    return transactions

# Fetch list of ERC-20 token addresses for a wallet
def get_erc20_token_addresses(address, api_key):
    url = f"https://api.etherscan.io/api?module=account&action=tokentx&address={address}&startblock=0&endblock=99999999&sort=asc&apikey={api_key}"
    response = requests.get(url)
    transactions = response.json().get('result', [])
    token_addresses = set(tx['contractAddress'] for tx in transactions if tx['tokenSymbol'])
    return list(token_addresses)

# Get ERC-20 token price in ETH and USD
def get_token_price(token_address):
    token_address = Web3.to_checksum_address(token_address)
    url = f"https://api.coingecko.com/api/v3/simple/token_price/ethereum?contract_addresses={token_address}&vs_currencies=eth,usd"
    response = requests.get(url)
    price_data = response.json()
    eth_price = price_data.get(token_address.lower(), {}).get('eth', 0)
    usd_price = price_data.get(token_address.lower(), {}).get('usd', 0)
    return eth_price, usd_price

# Filter substantial transactions
def filter_substantial_transactions(transactions, threshold_eth):
    threshold_wei = web3.to_wei(threshold_eth, 'ether')
    substantial_transactions = [tx for tx in transactions if int(tx['value']) > threshold_wei]
    return substantial_transactions

# Get NFT holders, limited to the first 10 holders
def get_nft_holders(contract_address, limit=10):
    contract_address = Web3.to_checksum_address(contract_address)
    contract = web3.eth.contract(address=contract_address, abi=erc721_abi)
    total_supply = contract.functions.totalSupply().call()
    
    holders = []
    for token_id in range(min(total_supply, limit)):
        owner = contract.functions.ownerOf(token_id).call()
        holders.append(owner)
    
    return holders

# Calculate total value of assets
def calculate_total_value(addresses, api_key):
    total_value_eth = 0
    total_value_usd = 0
    token_details = {}

    for address in addresses:
        # Get ETH balance
        balance_eth = get_wallet_balance(address)
        logging.info(f"ETH Balance for {address}: {balance_eth} ETH")
        total_value_eth += float(balance_eth)
        
        # Get ERC-20 token balances and convert to ETH and USD
        token_addresses = get_erc20_token_addresses(address, api_key)
        for token_address in token_addresses:
            balance = get_erc20_balance(address, token_address)
            price_in_eth, price_in_usd = get_token_price(token_address)
            token_value_eth = balance * price_in_eth
            token_value_usd = balance * price_in_usd
            name, symbol = get_token_name_symbol(token_address)
            
            logging.info(f"Token Balance for {name} ({symbol}): {balance}, Price in ETH: {price_in_eth}, Value in ETH: {token_value_eth}, Value in USD: {token_value_usd}")

            if token_address not in token_details:
                token_details[token_address] = {
                    'name': name,
                    'symbol': symbol,
                    'balance': balance,
                    'eth_value': token_value_eth,
                    'usd_value': token_value_usd
                }
            else:
                token_details[token_address]['balance'] += balance
                token_details[token_address]['eth_value'] += token_value_eth
                token_details[token_address]['usd_value'] += token_value_usd

            total_value_eth += token_value_eth
            total_value_usd += token_value_usd

    return total_value_eth, total_value_usd, token_details

def main():
    wallet_address = '[test wallet address]'  # Address to analyze
    threshold_eth = 1  # Ether
    etherscan_api_key = '[Replace with yours]'
    nft_contract_address = '0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d'  # Bored Apes Yacht Club contract address
    cache_file_path = 'cached_data.json'

    # Load cached data if available and fresh
    total_value_eth, total_value_usd, token_details = load_cached_data(cache_file_path)

    if total_value_eth is None or total_value_usd is None or token_details is None:
        # Step 1: Fetch wallet balance and token holdings
        balance = get_wallet_balance(wallet_address)
        print(f"Wallet Balance: {balance} ETH")

        # Step 2: Fetch transaction history
        transactions = get_transaction_history(wallet_address, etherscan_api_key)

        # Step 3: Filter substantial transactions
        if transactions and isinstance(transactions, list) and all(isinstance(tx, dict) for tx in transactions):
            substantial_transactions = filter_substantial_transactions(transactions, threshold_eth)
            print(f"Substantial Transactions: {len(substantial_transactions)}")
        else:
            print("Error: Unexpected format of transactions data")
            print(transactions)

        # Step 4: Load NFT project wallets, limited to the first 10 holders
        nft_holders = get_nft_holders(nft_contract_address, limit=2)
        print(f"NFT Holders: {len(nft_holders)}")

        # Step 5: Calculate total value of all assets
        total_value_eth, total_value_usd, token_details = calculate_total_value(nft_holders, etherscan_api_key)
        print(f"Total Value of Assets: {total_value_eth} ETH, {total_value_usd} USD")

        # Save the calculated data to the cache
        save_cached_data(cache_file_path, total_value_eth, total_value_usd, token_details)
    else:
        print("Loaded data from cache.")
        print(f"Total Value of Assets: {total_value_eth} ETH, {total_value_usd} USD")

    # Print details of each ERC-20 asset
    print("\nERC-20 Assets Details:")
    for token_address, details in token_details.items():
        print(f"Token Name: {details['name']} ({details['symbol']}), Balance: {details['balance']}, Value in ETH: {details['eth_value']}, Value in USD: {details['usd_value']}")

if __name__ == "__main__":
    main()
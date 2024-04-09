import json
#from datamodel import OrderDepth, UserId, TradingState, Order
from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState

from typing import List
from typing import Any
import string
import math
from logger import Logger  # Assuming Logger is properly defined and imported

AMETHYSTS = 'AMETHYSTS'
STARFRUIT = 'STARFRUIT'
SUBMISSION = 'SUBMISSION'  # Used for identifying trades involving this submission

PRODUCTS = [AMETHYSTS, STARFRUIT]

DEFAULT_PRICES = {
    AMETHYSTS: 10_000,
    STARFRUIT: 5_000,
}


class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(self.to_json([
            self.compress_state(state, ""),
            self.compress_orders(orders),
            conversions,
            "",
            "",
        ]))

        # We truncate state.traderData, trader_data, and self.logs to the same max. length to fit the log limit
        max_item_length = (self.max_log_length - base_length) // 3

        print(self.to_json([
            self.compress_state(state, self.truncate(state.traderData, max_item_length)),
            self.compress_orders(orders),
            conversions,
            self.truncate(trader_data, max_item_length),
            self.truncate(self.logs, max_item_length),
        ]))

        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        compressed = []
        for listing in listings.values():
            compressed.append([listing["symbol"], listing["product"], listing["denomination"]])

        return compressed

    def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        compressed = {}
        for symbol, order_depth in order_depths.items():
            compressed[symbol] = [order_depth.buy_orders, order_depth.sell_orders]

        return compressed

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
        compressed = []
        for arr in trades.values():
            for trade in arr:
                compressed.append([
                    trade.symbol,
                    trade.price,
                    trade.quantity,
                    trade.buyer,
                    trade.seller,
                    trade.timestamp,
                ])

        return compressed

    def compress_observations(self, observations: Observation) -> list[Any]:
        conversion_observations = {}
        for product, observation in observations.conversionObservations.items():
            conversion_observations[product] = [
                observation.bidPrice,
                observation.askPrice,
                observation.transportFees,
                observation.exportTariff,
                observation.importTariff,
                observation.sunlight,
                observation.humidity,
            ]

        return [observations.plainValueObservations, conversion_observations]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
        compressed = []
        for arr in orders.values():
            for order in arr:
                compressed.append([order.symbol, order.price, order.quantity])

        return compressed

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        if len(value) <= max_length:
            return value

        return value[:max_length - 3] + "..."

logger = Logger()

class Trader:
    def __init__(self) -> None:
        self.logger = Logger()  # Initialize the logger
        print("Initialize Trader ...")
        self.position_limit = {
            AMETHYSTS: 20,
            STARFRUIT: 20,
        }
        self.round = 0
        self.cash = 0
        self.past_prices = {product: [] for product in PRODUCTS}
        self.ema_prices = {product: None for product in PRODUCTS}
        self.ema_param = 0.5

    def get_position(self, product, state: TradingState):
        return state.position.get(product, 0)
    
    def get_mid_price(self, product, state: TradingState):
        default_price = self.ema_prices[product] if self.ema_prices[product] is not None else DEFAULT_PRICES[product]
        if product not in state.order_depths:
            return default_price
        market_bids = state.order_depths[product].buy_orders
        market_asks = state.order_depths[product].sell_orders
        if len(market_bids) == 0 or len(market_asks) == 0:
            return default_price
        best_bid = max(market_bids)
        best_ask = min(market_asks)
        return (best_bid + best_ask) / 2
    
    def get_value_on_product(self, product, state: TradingState):
        return self.get_position(product, state) * self.get_mid_price(product, state)
    
    def get_best_bid_ask(self, product, state: TradingState):
        if product not in state.order_depths:
            return None, None
        market_bids = state.order_depths[product].buy_orders
        market_asks = state.order_depths[product].sell_orders
        if len(market_bids) == 0 or len(market_asks) == 0:
            return None, None
        best_bid = max(market_bids)
        best_ask = min(market_asks)
        return best_bid, best_ask
    
    def update_ema_price(self, state: TradingState):
        for product in PRODUCTS:
            mid_price = self.get_mid_price(product, state)
            if mid_price is None:
                continue
            if self.ema_prices[product] is None:
                self.ema_prices[product] = mid_price
            else:
                self.ema_prices[product] = self.ema_param * mid_price + (1 - self.ema_param) * self.ema_prices[product]
        self.logger.print(f"Updated EMA Prices: {self.ema_prices}")
    
    def amethyst_strategy(self, state: TradingState):

        self.logger.print("Executing Amethyst strategy")
        position_amethysts = self.get_position(AMETHYSTS, state) #get the position we currently have in AMETHYSTS

        bid_volume = self.position_limit[AMETHYSTS] - position_amethysts #find the bid volume as the position limit (20) - the current position we have in AMETHYSTS 
        ask_volume = - self.position_limit[AMETHYSTS] - position_amethysts # NOTE: This is a negative value bc enters into the SELL orders

        orders = [] #initialize an empty list containing the BUY and SELL orders
                    #To create a BUY order append : (PRODUCT, MAXIMUM BUY PRICE, + QUANTITY)
                    #To create a SELL order append : (PRODUCT, MINIMUM SELL PRICE, - QUANTITY)
        
        #The way my AMETHYSTS strategy works is by doing Market Making -> I place a BUY order at DEFAULT_PRICE - 1 abd a SELL order at DEFAULT_PRICE + 1
        
        #orders.append(Order(AMETHYSTS, DEFAULT_PRICES[AMETHYSTS] - 1, bid_volume))
        #orders.append(Order(AMETHYSTS, DEFAULT_PRICES[AMETHYSTS] + 1, ask_volume))
        
        orders.append(Order(AMETHYSTS, DEFAULT_PRICES[AMETHYSTS] - 2, bid_volume))
        orders.append(Order(AMETHYSTS, DEFAULT_PRICES[AMETHYSTS] + 2, ask_volume))

        return orders
    
    def starfruit_strategy(self, state: TradingState):
        self.logger.print("Executing Starfruit strategy")
        position_starfruit = self.get_position(STARFRUIT, state) #get the position we currently have in STARFRUIT
        
        bid_volume = self.position_limit[STARFRUIT] - position_starfruit #find the bid volume as the position limit (20) - the current position we have in STARFRUIT 
        ask_volume = - self.position_limit[STARFRUIT] - position_starfruit # NOTE: This is a negative value bc enters into the SELL orders

        orders = [] #initialize an empty list containing the BUY and SELL orders

        if position_starfruit == 0:
            # Not long nor short
            orders.append(Order(STARFRUIT, math.floor(self.ema_prices[STARFRUIT] - 1), bid_volume))
            orders.append(Order(STARFRUIT, math.ceil(self.ema_prices[STARFRUIT] + 1), ask_volume))
        
        if position_starfruit > 0:
            # Long position
            orders.append(Order(STARFRUIT, math.floor(self.ema_prices[STARFRUIT] - 2), bid_volume))
            orders.append(Order(STARFRUIT, math.ceil(self.ema_prices[STARFRUIT]), ask_volume))

        if position_starfruit < 0:
            # Short position
            orders.append(Order(STARFRUIT, math.floor(self.ema_prices[STARFRUIT]), bid_volume))
            orders.append(Order(STARFRUIT, math.ceil(self.ema_prices[STARFRUIT] + 2), ask_volume))

        return orders
    
    def run(self, state: TradingState):
        self.round += 1
        self.logger.print(f"Round: {self.round}, Timestamp: {state.timestamp}")
        
        self.update_ema_price(state)
        
        result = {}
        
        # Implementing AMETHYSTS Strategy
        try:
            result[AMETHYSTS] = self.amethyst_strategy(state)
        except Exception as e:
            self.logger.print(f"Error in AMETHYSTS strategy: {e}")
        
        # Implementing STARFRUIT Strategy
        try:
            result[STARFRUIT] = self.starfruit_strategy(state)
        except Exception as e:
            self.logger.print(f"Error in STARFRUIT strategy: {e}")
        
        conversions = 0  # Update according to your strategy
        trader_data = "Your custom trader data here"
        
        # Flush logs to output
        self.logger.flush(state, result, conversions, trader_data)
        
        return result, conversions, trader_data

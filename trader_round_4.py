import json
#from datamodel import OrderDepth, UserId, TradingState, Order
from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState, ConversionObservation

from typing import Any, Dict, List, Union
import string
import math
import numpy as np
import pandas as pd
#from logger import logger  # Assuming Logger is properly defined and imported

AMETHYSTS = 'AMETHYSTS'
STARFRUIT = 'STARFRUIT'
ORCHIDS= 'ORCHIDS'
GIFT_BASKET='GIFT_BASKET'
ROSES='ROSES'
CHOCOLATE='CHOCOLATE'
STRAWBERRIES='STRAWBERRIES'
SUBMISSION = 'SUBMISSION'
COCONUT = 'COCONUT'
COCONUT_COUPON = 'COCONUT_COUPON'

PRODUCTS = [
    AMETHYSTS, 
    STARFRUIT, 
    ORCHIDS, 
    GIFT_BASKET, 
    ROSES, 
    CHOCOLATE, 
    STRAWBERRIES, 
    COCONUT,
    COCONUT_COUPON
]

DEFAULT_PRICES = {
    AMETHYSTS: 10_000,
    STARFRUIT: 5_000,
    ORCHIDS: 1_100,
    GIFT_BASKET:70_700,
    ROSES:14_500,
    CHOCOLATE:7_915,
    STRAWBERRIES:4_030,
    COCONUT: 1_000,
    COCONUT_COUPON: 635
}

POSITION_LIMITS = {
        AMETHYSTS: 20,
        STARFRUIT: 20,
        ORCHIDS: 20,
        GIFT_BASKET:60,
        ROSES:60,
        CHOCOLATE:250,
        STRAWBERRIES:350,
        COCONUT:300,
        COCONUT_COUPON:600
}

VOLUME_BASKET = 2
VOLUME_COCONUT = 2
SPREAD_THRESHOLD = 1.96
ROLLING_WINDOW = 200
MULTIPLIER = 3


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
            ORCHIDS: 20,
            GIFT_BASKET:60,
            ROSES:60,
            CHOCOLATE:250,
            STRAWBERRIES:350, 
            COCONUT:300,
            COCONUT_COUPON:600
        }

        self.round = 0
        self.cash = 0
        self.past_prices = {product: [] for product in PRODUCTS}
        self.ema_prices = {product: None for product in PRODUCTS}
        self.ema_param = 0.5
        self.theta=[ 9.758,  6.402, -5.561, 3.320, 1.501,  1.753]
        self.sunlight = [] #here we will store the sunlight time series for orchids
        self.humidity = [] #here we will store the humidity time series for orchids
        self.spread = []
        self.coco_spread = []

    #ROUND 1 UTILS
    def get_position(self, product, state: TradingState):
        return state.position.get(product, 0)
    
    def get_mid_price(self, product, state : TradingState):
        """
        Given a product and a state objects, it returns the mid_price.
        The mid_price consists of the price in between the best bid and the best ask.
        If there are no bids or asks, it returns the DEFAULT_PRICE consisting of the exponential moving average (EMA) of all the previous prices.
        """

        default_price = self.ema_prices[product]
        if default_price is None:
            default_price = DEFAULT_PRICES[product] #at the beginning of the series, just set the default price to DEFAULT_PRICE

        if product not in state.order_depths:
            return default_price
        
        market_bids = state.order_depths[product].buy_orders #save here all the BIDS present in the market for a product at a certain state in time
        if len(market_bids) == 0:
            return default_price #if there are no BID orders, set the mid_price to be the EMA of the previous prices
        
        market_asks = state.order_depths[product].sell_orders
        if len(market_asks) == 0:
            return default_price #if there are no ASK orders, set the mid_price to be the EMA of the previous prices
        
        #in all the other cased, the mid_price of a product at a given state in time is defined as
        #the average between the best bid and the best ask
        best_bid = max(market_bids)
        best_ask = max(market_asks)

        return (best_bid + best_ask)/2
    
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
        

    def reset_positions(self, state: TradingState, product):
        """
        this method allows to reset the position of a product to zero.

        """
        position = self.get_position(product, state)
        mid_price = int(round(self.get_mid_price(product, state)))
        best_bid, best_ask = self.get_best_bid_ask(product, state)

        if position >= 0:
            return Order(product, best_bid, -position)
        else:
            return Order(product, best_ask, -position)  
   

    #ROUND 3 UTILS
    def update_spread(self, state: TradingState):
        """
        this method appends the spread value to the self.spread list at each state
        """
        price_strawberries = self.get_mid_price(STRAWBERRIES, state)
        price_chocolate = self.get_mid_price(CHOCOLATE, state)
        price_roses = self.get_mid_price(ROSES, state)
        price_basket = self.get_mid_price(GIFT_BASKET, state)

        current_spread = price_basket - (4 * price_chocolate + 6 * price_strawberries + price_roses)

        self.spread.append(current_spread)


    #ROUND 1 STRATEGIES
    def amethyst_strategy(self, state: TradingState):

        self.logger.print("Executing Amethyst strategy")
        position_amethysts = self.get_position(AMETHYSTS, state) #get the position we currently have in AMETHYSTS

        bid_volume = self.position_limit[AMETHYSTS] - position_amethysts #find the bid volume as the position limit (20) - the current position we have in AMETHYSTS 
        ask_volume = - self.position_limit[AMETHYSTS] - position_amethysts # NOTE: This is a negative value bc enters into the SELL orders

        best_bid, best_ask = self.get_best_bid_ask(AMETHYSTS, state) #get the best bid and ask currently in hte orderbook

        orders = []
        
        if best_bid > DEFAULT_PRICES[AMETHYSTS] and best_ask > DEFAULT_PRICES[AMETHYSTS]:
            orders.append(Order(AMETHYSTS, DEFAULT_PRICES[AMETHYSTS], bid_volume)) #buy at 10K
            orders.append(Order(AMETHYSTS, best_bid, ask_volume)) #sell at best_bid

        elif best_bid < DEFAULT_PRICES[AMETHYSTS] and best_ask < DEFAULT_PRICES[AMETHYSTS]:
            orders.append(Order(AMETHYSTS, best_ask, bid_volume)) #buy at best_ask
            orders.append(Order(AMETHYSTS, DEFAULT_PRICES[AMETHYSTS], ask_volume)) #sell at 10K

        else: # make the market at with the largest spread between our buy and sell orders
            bid_diff = abs(best_bid - DEFAULT_PRICES[AMETHYSTS])
            ask_diff = abs(DEFAULT_PRICES[AMETHYSTS] - best_ask)
            min_diff = min(bid_diff, ask_diff)

            orders.append(Order(AMETHYSTS, DEFAULT_PRICES[AMETHYSTS] - min_diff + 1, bid_volume)) #buy
            orders.append(Order(AMETHYSTS, DEFAULT_PRICES[AMETHYSTS] + min_diff - 1, ask_volume)) #sell
            
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


    #ROUND 2 STRATEGIES
    def orchids_strategy(self, state: TradingState, sunlight, humidity):
        self.logger.print("Executing Orchids strategy")

        current_timestamp = int(state.timestamp)

        position_orchids = self.get_position(ORCHIDS, state)
        bid_volume = self.position_limit[ORCHIDS] - position_orchids
        ask_volume = -self.position_limit[ORCHIDS] - position_orchids

        best_bid, best_ask = self.get_best_bid_ask(ORCHIDS, state)

        mid_price = int(round(self.get_mid_price(ORCHIDS, state)))

        sunlight_deriv = None
        humidity_deriv = None

        # Calculate derivatives if there are enough data points
        if len(sunlight) >= 20:
            sunlight_deriv = sunlight[-1] - sunlight[-20]
        if len(humidity) >= 20:
            humidity_deriv = humidity[-1] - humidity[-20]
        
        self.logger.print(f"Sunlight Derivative: {sunlight_deriv}, Humidity Derivative: {humidity_deriv}")

        orders = []

        if current_timestamp <= 900_000:
        # If both sunlight and humidity are increasing 
            if sunlight_deriv is not None and humidity_deriv is not None:
                if sunlight_deriv > 0 and humidity_deriv > 0:
                    orders.append(Order(ORCHIDS, mid_price, bid_volume))

                # If both sunlight and humidity are decreasing 
                elif sunlight_deriv < 0 and humidity_deriv < 0:
                    orders.append(Order(ORCHIDS, mid_price, ask_volume))
                
                # As soon as the derivatives are discordant reset the position to 0
                else:
                    orders.append(self.reset_positions(state, ORCHIDS))  
                    
            if len(sunlight) < 20 or len(humidity) < 20 or sunlight_deriv is None or humidity_deriv is None:
                pass
        else:
            orders.append(self.reset_positions(state, ORCHIDS))

        return orders
    
        
    #ROUND 3      
    def choco_straw_rose_bask_strategy(self, state: TradingState):
        """ 
        gift_basket = 4 * chocolate + 6 * strawberries + roses
        """

        self.logger.print("Executing choco_straw_rose_bask_ strategy")

        orders_chocolate=[]
        orders_strawberries=[]
        orders_roses=[]
        orders_gift_basket=[]

        def create_orders(buy_basket: bool, multiplier):

            if buy_basket:
                sign = 1
                price_basket = 1_000_000
                price_others = 1
            else:
                sign = -1
                price_basket = 1
                price_others = 1_000_000
            
            orders_gift_basket.append(
                Order(GIFT_BASKET, price_basket, sign*VOLUME_BASKET*multiplier)
            )
            orders_chocolate.append(
                Order(CHOCOLATE, price_others, -sign*4*VOLUME_BASKET*multiplier)
            )
            orders_strawberries.append(
                Order(STRAWBERRIES, price_others, -sign*6*VOLUME_BASKET*multiplier)
            )
            orders_roses.append(
                Order(ROSES, price_others, -sign*VOLUME_BASKET*multiplier)
            )

        #calculate the mid prices of everything
        price_strawberries= self.get_mid_price(STRAWBERRIES, state)
        price_chocolate = self.get_mid_price(CHOCOLATE, state)
        price_roses = self.get_mid_price(ROSES, state)
        price_basket = self.get_mid_price(GIFT_BASKET, state)

        #calculate the spread at the current state
        spread = price_basket - (4 * price_chocolate + 6 * price_strawberries + price_roses)

        #get the current position we have on the GIFTS_BASKET
        position_basket = self.get_position(GIFT_BASKET, state)

        #calculate a time series of spread mean and stdev with rolling window size of ROLLING_WINDOW
        past_spreads = pd.Series(self.spread)
        spread_mean = past_spreads.rolling(ROLLING_WINDOW).mean()
        spread_sd = past_spreads.rolling(ROLLING_WINDOW).std()

        #calculate the average spread over a smaller window of 5 periods
        spread_5 =  past_spreads.rolling(5).mean()

        if not np.isnan(spread_mean.iloc[-1]): #if the last spread_mean is not a NaN, I will use the last values of the timeseries just calculated
            spread_mean = spread_mean.iloc[-1]
            spread_sd = spread_sd.iloc[-1]
            spread_5 = spread_5.iloc[-1]
           
            if abs(position_basket) <= POSITION_LIMITS[GIFT_BASKET] - VOLUME_BASKET: #if we can buy or sell other baskets:
                if spread_5 < spread_mean - SPREAD_THRESHOLD * spread_sd: #if the recent spread is more than 1.96 standard deviations below the mean, buy the basket and sell the components
                    buy_basket = True
                    create_orders(buy_basket, multiplier=1)
                elif spread_5 > spread_mean + SPREAD_THRESHOLD * spread_sd:
                    buy_basket = False
                    create_orders(buy_basket, multiplier=1)
                else:
                    pass

            else: #if we reached the maximum number of baskets we can buy or sell, decrease our position by multiplier basket
                if position_basket > 0: #in this case I want to sell a basket
                    buy_basket = False
                    create_orders(buy_basket, multiplier=MULTIPLIER)
                else: #in this case I want to buy a basket
                    buy_basket = True
                    create_orders(buy_basket, multiplier=MULTIPLIER)

        return orders_chocolate, orders_strawberries, orders_roses, orders_gift_basket

    #ROUND 4 UTILS
    def update_coco_spread(self, state: TradingState, LOOKBACK = 50):
        prices_coconut = self.past_prices[COCONUT]
        prices_coupon = self.past_prices[COCONUT_COUPON]

        if len(prices_coconut) < LOOKBACK or len(prices_coupon) < LOOKBACK:
            self.coco_spread.append(np.NaN)
        
        else:
            #get the average of the past 50 prices of coconut and coconut_coupon
            recent_prices_coconut = np.mean(prices_coconut[-LOOKBACK:])
            recent_prices_coupon = np.mean(prices_coupon[-LOOKBACK:])

            current_spread = recent_prices_coconut - recent_prices_coupon

            self.coco_spread.append(current_spread)

    #ROUND 4
    def coco_strategy(self, state: TradingState):
        """
        implement a strategy based on the spread between coconut and coconut_coupon.
        if the spread is greater than 1.5 standard deviations above the mean, sell coconut and buy coconut_coupon.
        if the spread is smaller than 1.5 standard deviations below the mean, sell coconut_coupon and buy coconut.
        avoid trading for the first 1000 timestamps to get a good estimate of the mean and standard deviation of the spread.
        """ 
        self.logger.print("Executing Coco strategy")

        position_coconut = self.get_position(COCONUT, state)
        position_coupon = self.get_position(COCONUT_COUPON, state)

        buy_volume_coconut = self.position_limit[COCONUT] - position_coconut
        sell_volume_coconut = - self.position_limit[COCONUT] - position_coconut

        mid_price_coconut = self.get_mid_price(COCONUT, state)
        mid_price_coupon = self.get_mid_price(COCONUT_COUPON, state)

        best_bid, best_ask = self.get_best_bid_ask(COCONUT, state)

        price_ratio = mid_price_coconut / mid_price_coupon

        spread_series = pd.Series(self.coco_spread)

        orders_coconut = []
        orders_coupon = []

        if len(spread_series) < 100:
            pass
    
        else:
            current_spread = spread_series.iloc[-1]
            spread_mean = np.mean(spread_series)
            spread_sd = np.std(spread_series)

            if current_spread > spread_mean + 1.5 * spread_sd:
                orders_coconut.append(Order(COCONUT, mid_price_coconut, sell_volume_coconut))
                #orders_coupon.append(Order(COCONUT_COUPON, best_ask, VOLUME_COCONUT))

            elif current_spread < spread_mean - 1.5 * spread_sd:
                orders_coconut.append(Order(COCONUT, mid_price_coconut, buy_volume_coconut))
                #orders_coupon.append(Order(COCONUT_COUPON, best_bid, -VOLUME_COCONUT))

            elif abs(current_spread) < 1.5:
                orders_coconut.append(self.reset_positions(state, COCONUT))
                #orders_coupon.append(self.reset_positions(state, COCONUT_COUPON))

            else:
                pass

        return orders_coconut, orders_coupon


    def run(self, state: TradingState):
        self.round += 1
        #self.logger.print(f"Round: {self.round}, Timestamp: {state.timestamp}")

        #update past_prices for COCONUT and COCONUT_COUPON
        self.past_prices[COCONUT].append(self.get_mid_price(COCONUT, state))
        self.past_prices[COCONUT_COUPON].append(self.get_mid_price(COCONUT_COUPON, state))

        self.update_ema_price(state)
        
        #append to self.sunlight and self.humidity the current values of sunlight and humidity
        self.sunlight.append(state.observations.conversionObservations[ORCHIDS].sunlight)
        self.humidity.append(state.observations.conversionObservations[ORCHIDS].humidity)

        self.update_spread(state)

        self.update_coco_spread(state)
        self.logger.print(f"COCONUT-COUPON Spread: {self.coco_spread}")

        print(f"TIMESTAMP: {state.timestamp}")
        
        result = {}

        '''
        try:
            result[AMETHYSTS] = self.amethyst_strategy(state)
        except Exception as e:
            self.logger.print(f"Error in AMETHYSTS strategy: {e}")
        
        # Implementing STARFRUIT Strategy
        try:
            result[STARFRUIT] = self.starfruit_strategy(state)
        except Exception as e:
            self.logger.print(f"Error in STARFRUIT strategy: {e}")
        '''
        
        '''
        try:
            result[ORCHIDS] = self.orchids_strategy(state, self.sunlight, self.humidity)
        except Exception as e:
            self.logger.print(f"Error in ORCHIDS strategy: {e}")
        '''
        
        '''
        try:
            result[CHOCOLATE], \
            result[STRAWBERRIES], \
            result[ROSES], \
            result[GIFT_BASKET] = self.choco_straw_rose_bask_strategy(state)
        except Exception as e:
            self.logger.print(f"Error in choco_straw_rose_bask strategy: {e}")
        '''

        try:
            result[COCONUT], \
            result[COCONUT_COUPON] = self.coco_strategy(state)
        except Exception as e:
            self.logger.print(f"Error in coco strategy: {e}")
        

        conversions = 0 
        trader_data = "SAMPLE"
        
        # Flush logs to output
        self.logger.flush(state, result, conversions, trader_data)
        
        return result, conversions, trader_data
from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string
import math

#store the products names into variables to avoid typos
AMETHYSTS = 'AMETHYSTS'
STARFRUIT = 'STARFRUIT'
SUBMISSION = 'SUBMISSION' # idk what this is

#define a 'PRODUCTS' list
PRODUCTS = [
    AMETHYSTS,
    STARFRUIT,
]

#define default prices for amethysts and starfruit
DEFAULT_PRICES = {
    AMETHYSTS : 10_000,
    STARFRUIT : 5_000, 
}



class Trader:

    #initialize variables ecc. belonging to Trader class
    def __init__(self) -> None:
        
        print("Initialize Trader ...")

        #initialize the maximum amount of products we allow ourselves to own at each point in time (Risk Management)
        self.position_limit = {
            AMETHYSTS : 20,
            STARFRUIT : 20, 
        }

        self.round = 0
        self.cash = 0
        
        #initialize the list of all the past prices at each iteration for each PRODUCT: (here we are just inintializing it)
        self.past_prices = dict()
        for product in PRODUCTS:
            self.past_prices[product] = []
       
        #initialize the a list containing, for each product, the ema prices
        self.ema_prices = dict()
        for product in PRODUCTS:
            self.ema_prices[product] = None

        #initialize the ema parameter
        self.ema_param = 0.5
        

    #(UTILS) : define methods that will be used in the trading strategy
    def get_position(self, product, state : TradingState):
        """
        Given a product and a state objects, it returns the position we currently have on that product 
        """
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
    
    def get_value_on_product(self, product, state : TradingState):
        """
        Given a product and a state , it returns the amount of MONEY currently on the product
        """
        return self.get_position(product, state) * self.get_mid_price(product, state)
    
    def get_best_bid_ask(self, product, state : TradingState):
        """
        Given a product and a state, it returns the best bid and the best ask
        """
        if product not in state.order_depths:
            return None, None
        
        market_bids = state.order_depths[product].buy_orders
        market_asks = state.order_depths[product].sell_orders
        
        if len(market_bids) == 0 or len(market_asks) == 0:
            return None, None
        
        best_bid = max(market_bids)
        best_ask = min(market_asks)
        
        return best_bid, best_ask
        
    
    def update_pnl(self, state : TradingState):
        """
        Update PnL
        """
        def update_cash():
            for product in state.own_trades:
                for trade in state.own_trades[product]:
                    if trade.timestamp != state.timestamp - 100: #if trade was already analyzed
                        continue

                    if trade.buyer == SUBMISSION:
                        self.cash -= trade.quantity * trade.price
                    if trade.seller == SUBMISSION:
                        self.cash += trade.quantity * trade.price
            
        def get_value_on_position():
            value = 0
            for product in state.position:
                value += self.get_value_on_product(product, state)
            return value
        
        update_cash()
        return self.cash + get_value_on_position()
    
    def update_ema_price(self, state : TradingState):
        """
        Update the exponential moving average of the prices of each product
        """
        for product in PRODUCTS:
            mid_price = self.get_mid_price(product, state)
            if mid_price is None:
                continue
            
            #update ema price
            if self.ema_prices[product] is None:
                self.ema_prices[product] = mid_price
            else:
                self.ema_prices[product] = self.ema_param * mid_price + (1-self.ema_param) * self.ema_prices[product]       

    def amethyst_strategy(self, state: TradingState):
        """
        Here we define the strategy to trade AMETHYSTS. (Market Making Strategy) 
        This method will be called into 'run' to generate BUY or SELL signals for AMETHYSTS.
        Idea: BUY when the best BID is < DEFAULT_PRICE (Buy all the available volume)
              SELL when the best ASK is > DEFAULT_PRICE (Sell all the possible volume)
        """
        
        position_amethysts = self.get_position(AMETHYSTS, state) #get the position we currently have in AMETHYSTS

        bid_volume = self.position_limit[AMETHYSTS] - position_amethysts #find the bid volume as the position limit (20) - the current position we have in AMETHYSTS 
        ask_volume = - self.position_limit[AMETHYSTS] - position_amethysts # NOTE: This is a negative value bc enters into the SELL orders

        best_bid, best_ask = self.get_best_bid_ask(AMETHYSTS, state) #get the best bid and ask currently in hte orderbook

        orders = [] #initialize an empty list containing the BUY and SELL orders
                    #To create a BUY order append : (PRODUCT, MAXIMUM BUY PRICE, + QUANTITY)
                    #To create a SELL order append : (PRODUCT, MINIMUM SELL PRICE, - QUANTITY)
        
        #The way my AMETHYSTS strategy works is by doing Market Making -> I place a BUY order at DEFAULT_PRICE - 1 abd a SELL order at DEFAULT_PRICE + 1
        
        #orders.append(Order(AMETHYSTS, DEFAULT_PRICES[AMETHYSTS] - 1, bid_volume))
        #orders.append(Order(AMETHYSTS, DEFAULT_PRICES[AMETHYSTS] + 1, ask_volume))
        
        #orders.append(Order(AMETHYSTS, DEFAULT_PRICES[AMETHYSTS] - 2, bid_volume))
        #orders.append(Order(AMETHYSTS, DEFAULT_PRICES[AMETHYSTS] + 2, ask_volume))

        #new strategy
        if best_bid > DEFAULT_PRICES[AMETHYSTS] & best_ask > DEFAULT_PRICES[AMETHYSTS]:
            orders.append(Order(AMETHYSTS, DEFAULT_PRICES[AMETHYSTS], bid_volume)) #buy at 10K
            orders.append(Order(AMETHYSTS, best_bid, ask_volume)) #sell at best_bid

        if best_bid < DEFAULT_PRICES[AMETHYSTS] & best_ask < DEFAULT_PRICES[AMETHYSTS]:
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
        """
        Here we define the strategy to trade STARFRUIT. (Trend following stategy) 
        This method will be called into 'run' to generate BUY or SELL signals for STARFRUIT.
        Idea: Calculate the 'fair_price' for STARFRUIT with a linear regression over the previous few prices.
              BUY if BEST ASK < fair_price (Buy all the available volume)
              SELL if BEST BID > fair_price (Sell all the possible volume)
        """

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
        """
        Only method required. It takes all buy and sell orders for all symbols as an input, and outputs a list of orders to be sent
        """
        
        print("traderData: " + state.traderData)
        print("Observations: " + str(state.observations))
        print("Timestamp: " + str(state.timestamp))

        
        
        #self.round += 1
        #pnl = self.update_pnl(state)
        #self.update_ema_prices(state)

        #print(f"Log round {self.round}")

        """
        print("TRADES:")
        for product in state.own_trades:
            for trade in state.own_trades[product]:
                if trade.timestamp == state.timestamp - 100:
                    print(trade)
        """

        """
        result = {}
        
        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            acceptable_price = 10;  # TODO: Participant should calculate this value
            print("Acceptable price : " + str(acceptable_price))
            print("Buy Order depth : " + str(len(order_depth.buy_orders)) + ", Sell order depth : " + str(len(order_depth.sell_orders)))
    
            if len(order_depth.sell_orders) != 0: # If there are sell orders, I want to BUY
                best_ask, best_ask_amount = list(order_depth.sell_orders.items())[0]
                if int(best_ask) < acceptable_price:
                    print("BUY", str(-best_ask_amount) + "x", best_ask)
                    orders.append(Order(product, best_ask, -best_ask_amount))
    
            if len(order_depth.buy_orders) != 0: # If there are buy orders, I want to SELL
                best_bid, best_bid_amount = list(order_depth.buy_orders.items())[0]
                if int(best_bid) > acceptable_price:
                    print("SELL", str(best_bid_amount) + "x", best_bid)
                    orders.append(Order(product, best_bid, -best_bid_amount))
            
            result[product] = orders
    
    
        traderData = "SAMPLE" # String value holding Trader state data required. It will be delivered as TradingState.traderData on next execution.
        
        conversions = 1
        return result, conversions, traderData

        """

        self.round += 1
        self.update_ema_price(state)
        #self.update_fair_price(state)
        

        # Initialize the method output dict as an empty dict
        result = {}

        # AMETHYSTS STRATEGY
        amethysts_best_bid, amethysts_best_ask = self.get_best_bid_ask(AMETHYSTS, state)
        print("AMETHYSTS Best Bid: " + str(amethysts_best_bid))
        print("AMETHYSTS Best Ask: " + str(amethysts_best_ask)) 
        try:
            result[AMETHYSTS] = self.amethyst_strategy(state)
        except Exception as e:
            print("Error in amethysts strategy")
            print(e)

        # STARFRUIT STRATEGY
        starfruit_best_bid, starfruit_best_ask = self.get_best_bid_ask(STARFRUIT, state)
        print("STARFRUIT Best Bid: " + str(starfruit_best_bid))
        print("STARFRUIT Best Ask: " + str(starfruit_best_ask)) 
        try:
            result[STARFRUIT] = self.starfruit_strategy(state)
        except Exception as e:
            print("Error in starfruit strategy")
            print(e)

        print("+---------------------------------+")

        traderData = "SAMPLE" # String value holding Trader state data required. It will be delivered as TradingState.traderData on next execution.
        
        conversions = 1
        return result, conversions, traderData

# Cryplative

We want to create a system for automate trading and strategy research. 

## The platform

The system need to be modular and contain different parts that can be used independently. Some of the parts should be:

* MarketFetcher: A module that fetches market data from binance and have a cache system to avoid fetching the same data multiple times. It should have a system to discard the last candle if its not closed yet.
* Trading strategies: There should have a consistent interface for trading strategies, in the way that every strategy can fetch the market data, accept some configuration, can store its state across different runs and can generate signals to buy or sell.
* Backtesting: A module that can backtest a strategy using historical data.
* Portfolio management: A module that can manage a portfolio of assets, track the performance and generate reports.
* Real Execution: A module that can execute trades on binance using the API.
* Paper Trading: A module that can simulate trades without actually executing them on the market, to test strategies in a risk-free environment.
* Routines: A module that can run the different parts of the system in a scheduled way, for example, to run the backtesting every day at a certain time, or to run the real execution every hour...

These parts need to be compatible with each other, so if we have a strategy that generates signals, we should be able to backtest it using the backtesting module, and then execute it in real trading or paper trading. The portfolio management should be able to track the performance of the strategy in both backtesting and real or paper trading.

The platform should support market orders but also limit orders with stop loss and take profit. We want to be able to test different order types and see how they perform in different market conditions.

A good technology to implement the platform could be python, because of the large number of libraries and tools available for data analysis, backtesting and trading.

## The strategy research

Using the platform, we want to start researching different trading strategies. We can search for strategies in the literature and the internet, and then implement them in our platform to test them.

We really want to try with different parameters and configurations to see how they perform. We can also try to combine different strategies to see if we can improve the performance.

Our goal is to grow our capital by finding and implementing profitable trading strategies. We want to be able to adapt to changing market conditions and continuously improve our strategies.

Once we have a strategy implemented, we need to classify the different strategies and what parameters are the best for them, so we will be building a database of strategies and their performance under different market conditions. This will help us to identify which strategies are more robust and which ones are more sensitive to market changes but also retrieve old strategies and their performance to compare with new ones.

At any point we can decide to add the strategies to the list of the ones that are working with real execution or with paper trading, to see how they perform in real market conditions. We can also decide to discard strategies that are not performing well and focus on the ones that are showing good results.


## The real portfolio

As we said, our goal is to grow our capital in a aggressive way, so we want to have a real portfolio where we can execute the strategies that are showing good results in paper trading. We want to be able to track the performance of our real portfolio and compare it with the performance of our paper trading and backtesting.

We want to be able to see how our portfolio is progressing over time, and how the different strategies are contributing to the overall performance. We also want to be able to see the drawdowns and the risk of our portfolio, so we can adjust our strategies if needed.

## System monitoring

The platform is a system organized over files. Strategies are just functions that can be executed by the system and the backtesting results are just json files that can be stored in the file system. This way we can have a simple and flexible way to manage our strategies and their results.

To have visibility over the system, we can create a static webapp with vite, react and chadcn-ui that can display the different strategies, their performance and the status of the real portfolio. 

We can create an API in pure bun.js that will serve the data from the file system to the webapp, so we can have a real-time view of our strategies and portfolio. The API can also allow to run strategies and backtesting in the platform from the webapp, so we can have a more interactive way to manage our system.
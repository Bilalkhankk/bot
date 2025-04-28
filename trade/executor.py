from data.fetcher import exchange
from config import settings

def place_order(symbol, side, amount, price, sl_price, tp_price):
    """Place order with stop loss and take profit"""
    try:
        # Set leverage first
        exchange.set_leverage(settings.LEVERAGE, symbol)
        
        # Place main order
        order = exchange.create_order(
            symbol=symbol,
            type='limit',
            side=side,
            amount=amount,
            price=price,
            params={
                'stopPrice': sl_price if side == 'sell' else None,
                'stopLimitPrice': sl_price if side == 'sell' else None
            }
        )
        
        # For futures, we'll use reduceOnly orders for TP/SL
        if side == 'buy':
            # Take profit order
            exchange.create_order(
                symbol=symbol,
                type='take_profit',
                side='sell',
                amount=amount,
                price=tp_price,
                params={'reduceOnly': True}
            )
            
            # Stop loss order
            exchange.create_order(
                symbol=symbol,
                type='stop',
                side='sell',
                amount=amount,
                price=sl_price,
                params={'reduceOnly': True}
            )
        else:  # sell
            # Take profit order
            exchange.create_order(
                symbol=symbol,
                type='take_profit',
                side='buy',
                amount=amount,
                price=tp_price,
                params={'reduceOnly': True}
            )
            
            # Stop loss order
            exchange.create_order(
                symbol=symbol,
                type='stop',
                side='buy',
                amount=amount,
                price=sl_price,
                params={'reduceOnly': True}
            )
            
        return order
    except Exception as e:
        print(f"Order error for {symbol}: {str(e)[:100]}")
        return None
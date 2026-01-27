#property strict

// ====== INPUT PARAMETERS ======
input string TradeSymbol          = "XRPUSD";
input int    MagicNumber          = 8852001;
input int    ExecTF               = PERIOD_H4;

// Indicators
input int    EMA_Slow             = 200;
input int    EMA_Mid              = 50;
input int    ATR_Period           = 14;
input int    RSI_Period           = 14;

// Entry Filters
input double Dev_ATR_Mult         = 3.0;
input double RSI_Oversold         = 28.0;
input double RSI_Overbought       = 72.0;
input double Min_ATR              = 0.005;

// Risk
input bool   UseFixedLots         = false;
input double FixedLots            = 0.10;
input double RiskPercent          = 1.0;
input double MinLots              = 0.01;
input double MaxLots              = 2.0;

// SL / TP
input double SL_ATR_Mult          = 1.4;
input double TP_ATR_Mult          = 2.2;

// Trade Control
input int    MinBarsBetweenTrades = 4;
input int    MaxOpenTrades        = 1;
input int    MaxSpreadPoints      = 3000;
input int    SlippagePoints       = 30;

// ====== GLOBAL ======
datetime lastTradeTime = 0;

// ====== LOT CALC ======
double CalcLot(double slPoints)
{
   if(UseFixedLots) return FixedLots;

   double riskMoney = AccountBalance() * RiskPercent / 100.0;
   double tickValue = MarketInfo(Symbol(), MODE_TICKVALUE);
   double lot = riskMoney / (slPoints * tickValue);

   lot = MathMax(MinLots, MathMin(lot, MaxLots));
   return NormalizeDouble(lot, 2);
}

// ====== OPEN COUNT ======
int CountPositions()
{
   int c = 0;
   for(int i=OrdersTotal()-1; i>=0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS))
         if(OrderMagicNumber()==MagicNumber && OrderSymbol()==Symbol())
            c++;
   }
   return c;
}

// ====== MAIN ======
void OnTick()
{
   if(Symbol() != TradeSymbol) return;
   if(Period() != ExecTF) return;
   if(CountPositions() >= MaxOpenTrades) return;
   if(TimeCurrent() - lastTradeTime < PeriodSeconds()*MinBarsBetweenTrades) return;

   if(MarketInfo(Symbol(), MODE_SPREAD) > MaxSpreadPoints) return;

   double ema200 = iMA(Symbol(), ExecTF, EMA_Slow, 0, MODE_EMA, PRICE_CLOSE, 1);
   double ema50  = iMA(Symbol(), ExecTF, EMA_Mid,  0, MODE_EMA, PRICE_CLOSE, 1);
   double atr    = iATR(Symbol(), ExecTF, ATR_Period, 1);
   double rsi    = iRSI(Symbol(), ExecTF, RSI_Period, PRICE_CLOSE, 1);
   double close  = iClose(Symbol(), ExecTF, 1);

   if(atr < Min_ATR) return;

   // ===== BUY =====
   if(close < ema200 - atr*Dev_ATR_Mult &&
      rsi < RSI_Oversold &&
      ema50 >= ema200)
   {
      double sl = close - atr*SL_ATR_Mult;
      double tp = close + atr*TP_ATR_Mult;
      double lot = CalcLot((close-sl)/Point);

      int ticket = OrderSend(Symbol(), OP_BUY, lot, Ask, SlippagePoints, sl, tp,
                             "XRP MeanRev BUY", MagicNumber, 0, clrBlue);
      if(ticket > 0) lastTradeTime = TimeCurrent();
   }

   // ===== SELL =====
   if(close > ema200 + atr*Dev_ATR_Mult &&
      rsi > RSI_Overbought &&
      ema50 <= ema200)
   {
      double sl = close + atr*SL_ATR_Mult;
      double tp = close - atr*TP_ATR_Mult;
      double lot = CalcLot((sl-close)/Point);

      int ticket = OrderSend(Symbol(), OP_SELL, lot, Bid, SlippagePoints, sl, tp,
                             "XRP MeanRev SELL", MagicNumber, 0, clrRed);
      if(ticket > 0) lastTradeTime = TimeCurrent();
   }
}

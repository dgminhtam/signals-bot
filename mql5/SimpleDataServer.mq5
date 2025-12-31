//+------------------------------------------------------------------+
//|                                             SimpleDataServer.mq5 |
//|                                                   SignalsBot Team|
//+------------------------------------------------------------------+
#property copyright "SignalsBot"
#property description "Socket Server for Signals Bot (using Ws2_32.dll)"
#property version   "3.11"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\SymbolInfo.mqh>

input int InpServerPort = 1122; // Server Port

// --- Wınsock 2.2 Imports ---
#define AF_INET         2
#define SOCK_STREAM     1
#define IPPROTO_TCP     6
#define INVALID_SOCKET  (uint)(~0)
#define SOCKET_ERROR    (-1)
#define FIONBIO         0x8004667E

#import "ws2_32.dll"
   int WSAStartup(ushort wVersionRequested, int &lpWSAData[]);
   int WSACleanup();
   uint socket(int af, int type, int protocol);
   int bind(uint s, int &name[], int namelen); 
   int listen(uint s, int backlog);
   uint accept(uint s, int &addr[], int &addrlen);
   int recv(uint s, uchar &buf[], int len, int flags);
   int send(uint s, uchar &buf[], int len, int flags);
   int closesocket(uint s);
   ushort htons(ushort hostshort);
   ulong inet_addr(const uchar &cp[]);
   int ioctlsocket(uint s, uint cmd, uint &argp);
   int WSAGetLastError();
#import

// Global Objects
CTrade m_trade;
CPositionInfo m_position;
CSymbolInfo m_symbol;
uint server_socket = INVALID_SOCKET;

// --- Helper: Prepare SockAddr ---
// sockaddr_in structure simulation using int array
// short sin_family; ushort sin_port; uint sin_addr; char sin_zero[8];
// Total 16 bytes = 4 integers.
void PrepareSockAddr(int &addr[], int port, string ip_str) {
   ArrayResize(addr, 4);
   ArrayInitialize(addr, 0);
   
   // Create uchar array for IP String
   uchar ip_chars[];
   StringToCharArray(ip_str, ip_chars);
   
   // sin_family (Low 16 bits of 1st int) = AF_INET
   // sin_port (High 16 bits of 1st int)
   // Warning: MQL5 integer layout is simple.
   // We construct: 
   // member 0: (sin_port << 16) | sin_family
   // member 1: sin_addr
   
   ushort s_port = htons((ushort)port);
   ulong s_addr = inet_addr(ip_chars);
   
   // Packing
   // Low 16 bits: Family, High 16 bits: Port
   addr[0] = (int)((s_port << 16) | AF_INET);
   addr[1] = (int)s_addr;
   addr[2] = 0;
   addr[3] = 0;
}

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   EventSetMillisecondTimer(10);
   ResetLastError();
   
   // 1. WSA Startup
   int wsaData[100]; // Buffer for WSAData
   int res = WSAStartup(0x0202, wsaData); // ver 2.2
   if(res != 0) {
      Print("❌ WSAStartup Failed. Error: ", res);
      return(INIT_FAILED);
   }
   
   // 2. Create Socket
   server_socket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
   if(server_socket == INVALID_SOCKET) {
      Print("❌ Socket Create Failed. LastError: ", WSAGetLastError());
      return(INIT_FAILED);
   }
   
   // 3. Set Non-Blocking Mode
   uint non_block = 1;
   if(ioctlsocket(server_socket, FIONBIO, non_block) != 0) {
      Print("❌ Ioctlsocket Failed. LastError: ", WSAGetLastError());
      return(INIT_FAILED);
   }
   
   // 4. Bind
   int addr[4];
   PrepareSockAddr(addr, InpServerPort, "127.0.0.1");
   
   if(bind(server_socket, addr, 16) == SOCKET_ERROR) {
      Print("❌ Bind Failed (Port ", InpServerPort, "). LastError: ", WSAGetLastError());
      return(INIT_FAILED);
   }
   
   // 5. Listen
   if(listen(server_socket, 5) == SOCKET_ERROR) {
      Print("❌ Listen Failed. LastError: ", WSAGetLastError());
      return(INIT_FAILED);
   }
   
   Print("✅ SimpleDataServer (Winsock) Started on Port: ", InpServerPort);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(server_socket != INVALID_SOCKET) {
      closesocket(server_socket);
   }
   WSACleanup();
   EventKillTimer();
   Print("🛑 SimpleDataServer Stopped.");
  }

//+------------------------------------------------------------------+
//| Timer event handler (Main Loop)                                  |
//+------------------------------------------------------------------+
void OnTimer()
  {
   if(server_socket == INVALID_SOCKET) return;
   
   int addr[4];
   int len = 16;
   
   // Accept connection (Non-blocking)
   uint client_sock = accept(server_socket, addr, len);
   
   if(client_sock != INVALID_SOCKET) {
      // Process Request immediately
      ProcessClient(client_sock);
   }
  }

//+------------------------------------------------------------------+
//| Process Client                                                   |
//+------------------------------------------------------------------+
void ProcessClient(uint client_sock) {
   uchar req_buf[4096];
   int bytes = recv(client_sock, req_buf, 4096, 0);
   
   if(bytes > 0) {
      string request = CharArrayToString(req_buf, 0, bytes, CP_UTF8);
      string response = HandleRequest(request);
      
      uchar resp_buf[];
      int resp_len = StringToCharArray(response, resp_buf, 0, WHOLE_ARRAY, CP_UTF8);
      
      // Send needs explicit length without null terminator usually, 
      // but MQL StringToCharArray adds \0. 
      // Python 'recv' ignores extra \0 usually or we strip it.
      // Let's send resp_len - 1 to avoid sending null terminator if we want clean text
      if(resp_len > 0) {
          send(client_sock, resp_buf, resp_len - 1, 0); 
      }
   }
   
   closesocket(client_sock);
}

// forward declaration
string ExecuteTradeRelative(string symbol, string type, double vol, double sl_points, double tp_points);
string GetTradeHistory(ulong ticket);

//+------------------------------------------------------------------+
//| Logic Handlers                                                   |
//+------------------------------------------------------------------+
string HandleRequest(string req) {
   string parts[];
   int count = StringSplit(req, '|', parts);
   if(count == 0) return "ERROR|EMPTY_REQUEST";
   string cmd = parts[0];
   
   if(count >= 3 && cmd != "ORDER" && cmd != "CHECK" && cmd != "CLOSE" && cmd != "DELETE" && cmd != "ORDER_REL") 
      return GetData(parts[0], parts[1], (int)StringToInteger(parts[2]));
      
   if(cmd == "ORDER" && count >= 4) {
      // CMD|SYMBOL|TYPE|VOL|SL|TP|PRICE
      double sl = (count > 4) ? StringToDouble(parts[4]) : 0.0;
      double tp = (count > 5) ? StringToDouble(parts[5]) : 0.0;
      double price = (count > 6) ? StringToDouble(parts[6]) : 0.0;
      
      return ExecuteTrade(parts[1], parts[2], StringToDouble(parts[3]), sl, tp, price);
   }
   
   if(cmd == "ORDER_REL" && count >= 6) {
      // ORDER_REL|SYMBOL|TYPE|VOL|SL_PTS|TP_PTS
      // parts[1]=Symbol, parts[2]=Types, parts[3]=Vol, parts[4]=SL_PTS, parts[5]=TP_PTS
      return ExecuteTradeRelative(parts[1], parts[2], StringToDouble(parts[3]), StringToDouble(parts[4]), StringToDouble(parts[5]));
   }
   
   if(cmd == "CHECK") return CheckPositions(parts[1]);
   if(cmd == "HISTORY") return GetTradeHistory((ulong)StringToInteger(parts[1]));
   if(cmd == "CLOSE") return CloseTrade((ulong)StringToInteger(parts[1]));
   if(cmd == "DELETE") return DeleteOrder((ulong)StringToInteger(parts[1]));
   
   return "ERROR|UNKNOWN_COMMAND";
}

string GetData(string symbol, string timeframe_str, int count) {
   ENUM_TIMEFRAMES tf = StringToTimeframe(timeframe_str);
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int copied = CopyRates(symbol, tf, 0, count, rates);
   if(copied <= 0) return "ERROR|NO_DATA";
   
   string result = "";
   for(int i=0; i<copied; i++) {
      string line = StringFormat("%I64d,%G,%G,%G,%G,%I64d", 
                                 rates[i].time, rates[i].open, rates[i].high, rates[i].low, rates[i].close, rates[i].tick_volume);
      result += line + ";";
   }
   return result;
}

string ExecuteTrade(string symbol, string type, double vol, double sl, double tp, double price) {
   ENUM_ORDER_TYPE order_type;
   bool is_pending = false;

   if(type == "BUY") order_type = ORDER_TYPE_BUY;
   else if (type == "SELL") order_type = ORDER_TYPE_SELL;
   else if (type == "BUY_STOP") { order_type = ORDER_TYPE_BUY_STOP; is_pending = true; }
   else if (type == "SELL_STOP") { order_type = ORDER_TYPE_SELL_STOP; is_pending = true; }
   else if (type == "BUY_LIMIT") { order_type = ORDER_TYPE_BUY_LIMIT; is_pending = true; }
   else if (type == "SELL_LIMIT") { order_type = ORDER_TYPE_SELL_LIMIT; is_pending = true; }
   else return "ERROR|INVALID_TYPE";
   
   if(!m_symbol.Name(symbol)) return "ERROR|INVALID_SYMBOL";
   m_symbol.RefreshRates();
   
   m_trade.SetExpertMagicNumber(123456);
   
   if(is_pending) {
       // Pending Order (Buy Stop / Sell Stop)
       // Price (entry) is mandatory
       if(price <= 0) return "ERROR|INVALID_PRICE_FOR_PENDING";
       
       if(m_trade.OrderOpen(symbol, order_type, vol, 0.0, price, sl, tp))
           return "SUCCESS|" + IntegerToString(m_trade.ResultOrder());
   } else {
       // Market Order
       double market_price = (order_type == ORDER_TYPE_BUY) ? m_symbol.Ask() : m_symbol.Bid();
       if(m_trade.PositionOpen(symbol, order_type, vol, market_price, sl, tp))
           return "SUCCESS|" + IntegerToString(m_trade.ResultOrder());
   }
   
   return "FAIL|" + IntegerToString(m_trade.ResultRetcode());
}

string ExecuteTradeRelative(string symbol, string type, double vol, double sl_points, double tp_points) {
   ENUM_ORDER_TYPE order_type;
   
   if(type == "BUY") order_type = ORDER_TYPE_BUY;
   else if (type == "SELL") order_type = ORDER_TYPE_SELL;
   else return "ERROR|INVALID_TYPE_REL";
   
   if(!m_symbol.Name(symbol)) return "ERROR|INVALID_SYMBOL";
   
   // Force Refresh
   if(!m_symbol.RefreshRates()) {
       // Try again once
       m_symbol.RefreshRates();
   }
   
   double entry_price = (order_type == ORDER_TYPE_BUY) ? m_symbol.Ask() : m_symbol.Bid();
   double point = m_symbol.Point();
   double sl = 0.0;
   double tp = 0.0;
   
   // Logic: BUY -> SL = Ask - Points*Point
   if(order_type == ORDER_TYPE_BUY) {
       sl = entry_price - (sl_points * point);
       tp = entry_price + (tp_points * point);
   } else {
       sl = entry_price + (sl_points * point);
       tp = entry_price - (tp_points * point);
   }
   
   // Normalization
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   sl = NormalizeDouble(sl, digits);
   tp = NormalizeDouble(tp, digits);
   
   m_trade.SetExpertMagicNumber(123456);
   
   if(m_trade.PositionOpen(symbol, order_type, vol, entry_price, sl, tp))
       return "SUCCESS|" + IntegerToString(m_trade.ResultOrder());
       
   return "FAIL|" + IntegerToString(m_trade.ResultRetcode());
}

string CheckPositions(string symbol) {
   string result = "";
   int total = PositionsTotal();
   for(int i=0; i<total; i++) {
      if(m_position.SelectByIndex(i)) {
         string pos_sym = m_position.Symbol();
         if(symbol == "ALL" || pos_sym == symbol) {
            string line = StringFormat("%I64d,%d,%.5f,%.2f,%.2f,%.5f,%.5f", 
               m_position.Ticket(), m_position.PositionType(), m_position.PriceOpen(), m_position.Volume(), m_position.Profit(),
               m_position.StopLoss(), m_position.TakeProfit());
            result += line + ";";
         }
      }
   }
   return result == "" ? "EMPTY" : result;
}

string CloseTrade(ulong ticket) {
   if(m_trade.PositionClose(ticket)) return "SUCCESS|CLOSED";
   return "FAIL|" + IntegerToString(m_trade.ResultRetcode());
}

string DeleteOrder(ulong ticket) {
    if(m_trade.OrderDelete(ticket)) return "SUCCESS|DELETED";
    return "FAIL|" + IntegerToString(m_trade.ResultRetcode());
}

string GetTradeHistory(ulong ticket) {
   if(!HistorySelectByPosition(ticket)) return "ERROR|HISTORY_NOT_FOUND";
   
   double open_price = 0.0;
   long open_time = 0;
   double close_price = 0.0;
   long close_time = 0;
   double total_profit = 0.0;
   double sl = 0.0;
   double tp = 0.0;
   
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++) {
      ulong deal_ticket = HistoryDealGetTicket(i);
      if(deal_ticket > 0) {
         long entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
         
         // 1. Tìm Deal Vào (Entry IN) để lấy Open Price/Time
         if(entry == DEAL_ENTRY_IN) {
            open_price = HistoryDealGetDouble(deal_ticket, DEAL_PRICE);
            open_time = HistoryDealGetInteger(deal_ticket, DEAL_TIME);
         }
         
         // 2. Tìm Deal Ra (Entry OUT) để lấy Close Price/Time/Profit
         if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_INOUT) {
            close_price = HistoryDealGetDouble(deal_ticket, DEAL_PRICE);
            close_time = HistoryDealGetInteger(deal_ticket, DEAL_TIME);
            
            double profit = HistoryDealGetDouble(deal_ticket, DEAL_PROFIT);
            double swap = HistoryDealGetDouble(deal_ticket, DEAL_SWAP);
            double comm = HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION);
            total_profit += profit + swap + comm;
            
            // SL/TP thường được ghi nhận ở deal đóng
            sl = HistoryDealGetDouble(deal_ticket, DEAL_SL);
            tp = HistoryDealGetDouble(deal_ticket, DEAL_TP);
         }
      }
   }
   
   // Format trả về: SUCCESS|O_PRICE|C_PRICE|PROFIT|SL|TP|O_TIME|C_TIME
   return "SUCCESS|" + 
          DoubleToString(open_price) + "|" + 
          DoubleToString(close_price) + "|" + 
          DoubleToString(total_profit, 2) + "|" + 
          DoubleToString(sl) + "|" + 
          DoubleToString(tp) + "|" + 
          IntegerToString(open_time) + "|" + 
          IntegerToString(close_time);
}

ENUM_TIMEFRAMES StringToTimeframe(string tf) {
   if(tf == "M1") return PERIOD_M1;
   if(tf == "M5") return PERIOD_M5;
   if(tf == "M15") return PERIOD_M15;
   if(tf == "M30") return PERIOD_M30;
   if(tf == "H1") return PERIOD_H1;
   if(tf == "H4") return PERIOD_H4;
   if(tf == "D1") return PERIOD_D1;
   return PERIOD_CURRENT;
}

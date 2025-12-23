import { useEffect, useRef } from 'react';
import { createChart, ColorType, CrosshairMode, type IChartApi, CandlestickSeries } from 'lightweight-charts';

// Define the shape of the data coming from the backend
interface StockDataObj {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface Props {
  data: StockDataObj[];
  symbol: string;
}

const TVChart = ({ data, symbol }: Props) => {
  // We need a ref to the HTML div where the chart will live
  const chartContainerRef = useRef<HTMLDivElement>(null);
  // We keep track of the chart instance so we don't create duplicates
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    // 1. Basic validations
    if (!chartContainerRef.current || data.length === 0) return;

    // 2. Clean up previous chart if it exists (prevents duplicates on re-renders)
    if (chartRef.current) {
        chartRef.current.remove();
    }

    // 3. Initialize Chart with TradingView-like styling
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#1a1a1a' }, // Match your dark theme
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: 'rgba(42, 46, 57, 0)', visible: false },
        horzLines: { color: 'rgba(42, 46, 57, 0.2)', visible: true },
      },
      width: chartContainerRef.current.clientWidth,
      height: 400, // Taller height for better viewing
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      timeScale: {
        borderColor: 'rgba(197, 203, 206, 0.4)',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    // 4. Create the Candlestick Series
    const candlestickSeries = chart.addSeries(CandlestickSeries,{
      upColor: '#26a69a', // Classic TV Green
      downColor: '#ef5350', // Classic TV Red
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    });

    // 5. Format Data for Lightweight Charts
    // It expects { time: 'YYYY-MM-DD', open: 1, high: 2, low: 0.5, close: 1.5 }
    const formattedData = data.map((d) => ({
      time: d.date.split('T')[0], // Extract just YYYY-MM-DD
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    candlestickSeries.setData(formattedData);
    
    // Fit the content to the screen initially
    chart.timeScale().fitContent();

    // 6. Add resize handler to make it responsive
    const handleResize = () => {
        if(chartContainerRef.current) {
            chart.applyOptions({ width: chartContainerRef.current.clientWidth });
        }
    };

    window.addEventListener('resize', handleResize);

    // 7. Cleanup function (runs when component unmounts)
    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [data]); // Re-run this effect if the 'data' prop changes

  return (
    <div style={{ marginBottom: '20px', position: 'relative' }}>
        {/* Watermark Overlay */}
        <div style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            fontSize: '60px',
            color: 'rgba(255, 255, 255, 0.05)',
            zIndex: 0,
            pointerEvents: 'none',
            fontWeight: 'bold'
        }}>
            {symbol}
        </div>
      {/* The chart attaches here */}
      <div ref={chartContainerRef} style={{ width: '100%', height: '400px' }} />
    </div>
  );
};

export default TVChart;
import { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, CrosshairMode, type IChartApi, CandlestickSeries, LineSeries, LineStyle, createSeriesMarkers } from 'lightweight-charts';

// Define the shape of the data coming from the backend
interface StockDataObj {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface Contraction {
  peak_date: string;
  peak_price: number;
  trough_date: string;
  trough_price: number;
  depth: number;
}

interface VCPAnalysis {
  contractions: Contraction[];
  highest_high: number;
  lowest_low: number;
  base_length_days: number;
  base_depth_percent: number;
  breakout_confirmed: boolean | string;
  current_price: number;
}

interface Props {
  data: StockDataObj[];
  symbol: string;
  vcpAnalysis?: VCPAnalysis | null;
}

const TVChart = ({ data, symbol, vcpAnalysis }: Props) => {
  // We need a ref to the HTML div where the chart will live
  const chartContainerRef = useRef<HTMLDivElement>(null);
  // We keep track of the chart instance so we don't create duplicates
  const chartRef = useRef<IChartApi | null>(null);
  // Toggle state for VCP overlay
  const [showVCP, setShowVCP] = useState(true);

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
      height: chartContainerRef.current.clientHeight,
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
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
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

    // 6. Add VCP Contraction Zones if available
    if (showVCP && vcpAnalysis && vcpAnalysis.contractions && vcpAnalysis.contractions.length > 0) {
      // Color palette for contractions (more vibrant colors)
      const colors = [
        '#FFC107',  // Amber
        '#2196F3',  // Blue
        '#9C27B0',  // Purple
        '#00BCD4',  // Cyan
      ];

      const markers: any[] = [];

      // Create a line series that will connect peak to trough to peak
      const vcpTrendLine = chart.addSeries(LineSeries, {
        color: '#ffffff',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });

      // Build the trend line data connecting all peaks and troughs
      const trendLineData: any[] = [];

      vcpAnalysis.contractions.forEach((contraction, index) => {
        const color = colors[index % colors.length];
        
        // Add peak and trough to trend line
        trendLineData.push(
          { time: contraction.peak_date, value: contraction.peak_price },
          { time: contraction.trough_date, value: contraction.trough_price }
        );

        // Add markers for peaks and troughs
        markers.push(
          {
            time: contraction.peak_date,
            position: 'aboveBar',
            color: color,
            shape: 'circle',
            text: `P${index + 1}`,
          },
          {
            time: contraction.trough_date,
            position: 'belowBar',
            color: color,
            shape: 'circle',
            text: `T${index + 1}`,
          }
        );

        // Draw horizontal dashed/dotted lines for peak and trough
        const peakDate = contraction.peak_date;
        const troughDate = contraction.trough_date;
        
        // Find indices in the data
        const peakIndex = formattedData.findIndex(d => d.time === peakDate);
        const troughIndex = formattedData.findIndex(d => d.time === troughDate);
        
        if (peakIndex !== -1 && troughIndex !== -1) {
          // Extend lines a bit beyond the contraction for visibility
          const startIdx = Math.max(0, peakIndex - 5);
          const endIdx = Math.min(formattedData.length - 1, troughIndex + 5);
          
          // Create peak line (dashed)
          const peakLineSeries = chart.addSeries(LineSeries, {
            color: color,
            lineWidth: 2,
            lineStyle: LineStyle.Dashed,
            priceLineVisible: false,
            lastValueVisible: false,
          });

          // Create trough line (dotted)
          const troughLineSeries = chart.addSeries(LineSeries, {
            color: color,
            lineWidth: 2,
            lineStyle: LineStyle.Dotted,
            priceLineVisible: false,
            lastValueVisible: false,
          });
          
          const peakLineData = [];
          const troughLineData = [];
          
          for (let i = startIdx; i <= endIdx; i++) {
            peakLineData.push({ time: formattedData[i].time, value: contraction.peak_price });
            troughLineData.push({ time: formattedData[i].time, value: contraction.trough_price });
          }
          
          peakLineSeries.setData(peakLineData);
          troughLineSeries.setData(troughLineData);
        }
      });

      // Sort trend line data by time and set it
      trendLineData.sort((a, b) => {
        if (a.time < b.time) return -1;
        if (a.time > b.time) return 1;
        return 0;
      });
      vcpTrendLine.setData(trendLineData);

      // Apply markers to candlestick series
      if (markers.length > 0) {
        createSeriesMarkers(candlestickSeries, markers);
      }

      // Add highest high and lowest low lines across the entire chart
      {/*if (vcpAnalysis.highest_high) {
        const highestHighLine = chart.addSeries(LineSeries, {
          color: '#4caf50',
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        
        // Draw across entire visible range
        const highLineData = formattedData.map(d => ({
          time: d.time,
          value: vcpAnalysis.highest_high
        }));
        highestHighLine.setData(highLineData);
      }

      *if (vcpAnalysis.lowest_low) {
        const lowestLowLine = chart.addSeries(LineSeries, {
          color: '#f44336',
          lineWidth: 2,
          lineStyle: LineStyle.Dashed,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        
        // Draw across entire visible range
        const lowLineData = formattedData.map(d => ({
          time: d.time,
          value: vcpAnalysis.lowest_low
        }));
        lowestLowLine.setData(lowLineData);
      }*/}
    }
    
    // Set visible range to the last year of data (or less if not enough data)
    // This is more efficient than fitContent() + setVisibleRange()
    if (formattedData.length > 0) {
      const lastDate = formattedData[formattedData.length - 1].time;
      
      // Calculate approximately 252 trading days ago (1 year)
      // This is faster than date calculations and findIndex searches
      const tradingDaysInYear = 252;
      const fromIndex = Math.max(0, formattedData.length - tradingDaysInYear);
      const fromDate = formattedData[fromIndex].time;
      
      // Set the visible range to show last year
      chart.timeScale().setVisibleRange({
        from: fromDate as any,
        to: lastDate as any,
      });
    } else {
      // Fallback to fitContent if no data
      chart.timeScale().fitContent();
    }

    // 7. Add resize handler to make it responsive
    const handleResize = () => {
        if(chartContainerRef.current) {
            chart.applyOptions({ width: chartContainerRef.current.clientWidth });
        }
    };

    window.addEventListener('resize', handleResize);

    // 8. Cleanup function (runs when component unmounts)
    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [data, vcpAnalysis, showVCP]); // Re-run this effect if the 'data', 'vcpAnalysis', or 'showVCP' prop changes

  return (
    <div style={{ marginBottom: '20px', position: 'relative' }}>
        {/* Toggle Button */}
        {vcpAnalysis && (
          <button
            onClick={() => setShowVCP(!showVCP)}
            style={{
              position: 'absolute',
              top: '10px',
              left: '10px',
              zIndex: 10,
              padding: '4px 10px',
              backgroundColor: showVCP ? '#4caf50' : '#666',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '12px',
              fontWeight: '500',
              boxShadow: '0 2px 5px rgba(0,0,0,0.3)',
              transition: 'background-color 0.3s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = showVCP ? '#45a049' : '#555';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = showVCP ? '#4caf50' : '#666';
            }}
          >
            {showVCP ? '✓ VCP' : 'VCP'}
          </button>
        )}
        
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
      <div ref={chartContainerRef} style={{ width: '100%', height: '100vh' }} />
    </div>
  );
};

export default TVChart;
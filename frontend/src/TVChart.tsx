import { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, CrosshairMode, type IChartApi, CandlestickSeries, LineSeries, LineStyle, HistogramSeries, createSeriesMarkers } from 'lightweight-charts';

// Integration with LightweightCharts from TradingView

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
  markers?: any[] | null;
  sepaMarkers?: any[] | null; // New prop for SEPA markers
}

const TVChart = ({ data, symbol, vcpAnalysis, markers, sepaMarkers }: Props) => {
  // We need a ref to the HTML div where the chart will live
  const chartContainerRef = useRef<HTMLDivElement>(null);
  // We keep track of the chart instance so we don't create duplicates
  const chartRef = useRef<IChartApi | null>(null);
  // Toggle state for VCP overlay
  const [showVCP, setShowVCP] = useState(true);
  const [showMarkers, setShowMarkers] = useState(true);
  // markers are provided by parent via props
  const [backtestMarkers, setBacktestMarkers] = useState<any[] | null>(markers || null);
  const [sepaBacktestMarkers, setSepaBacktestMarkers] = useState<any[] | null>(sepaMarkers || null);

  // Update local state when props change
  useEffect(() => {
    setBacktestMarkers(markers || null);
  }, [markers]);

  useEffect(() => {
    setSepaBacktestMarkers(sepaMarkers || null);
  }, [sepaMarkers]);

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
        background: { type: ColorType.Solid, color: '#1a1a1a' }, 
        textColor: '#d1d4dc',
        attributionLogo: false,
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

    // 4a. Create the Volume Series (Histogram overlay at the bottom)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: '', // set as an overlay by setting a blank priceScaleId
    });

    // Set the positioning of the volume series to the bottom 20% of the chart
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8, // highest point of the series will be 80% away from the top
        bottom: 0, // lowest point will be at the very bottom
      },
    });

    // Adjust the main candlestick series to not overlap with volume
    candlestickSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.1, // highest point will be 10% away from the top
        bottom: 0.25, // lowest point will be 25% away from the bottom (to leave room for volume)
      },
    });

    // 5. Format Data for Lightweight Charts
    let formattedData = data.map((d) => ({
      time: d.date.split('T')[0],
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
      volume: d.volume,
    }));

    // Remove duplicates and ensure ascending order by time
    const seenTimes = new Set<string>();
    formattedData = formattedData.filter((d) => {
      if (seenTimes.has(d.time)) {
        return false; // Skip duplicate timestamps
      }
      seenTimes.add(d.time);
      return true;
    });

    // Sort by time to ensure ascending order
    formattedData.sort((a, b) => {
      if (a.time < b.time) return -1;
      if (a.time > b.time) return 1;
      return 0;
    });

    // Only set data if we have valid candlestick data
    if (formattedData.length > 0) {
      candlestickSeries.setData(formattedData);
      
      // Format and set volume data for the histogram series
      // Color bars based on whether price closed up (green) or down (red)
      const volumeData = formattedData.map((d) => ({
        time: d.time,
        value: d.volume,
        color: d.close >= d.open ? '#26a69a' : '#ef5350', // Green for up, red for down
      }));
      
      if (volumeData.length > 0) {
        volumeSeries.setData(volumeData);
      }
    }

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
          
          if (peakLineData.length > 0) {
            peakLineSeries.setData(peakLineData);
          }
          if (troughLineData.length > 0) {
            troughLineSeries.setData(troughLineData);
          }
        }
      });

      // Sort trend line data by time and set it
      trendLineData.sort((a, b) => {
        if (a.time < b.time) return -1;
        if (a.time > b.time) return 1;
        return 0;
      });

      // Remove duplicates from trend line data
      const uniqueTrendLineData = [];
      const seenTrendTimes = new Set<string>();
      for (const point of trendLineData) {
        if (!seenTrendTimes.has(point.time)) {
          seenTrendTimes.add(point.time);
          uniqueTrendLineData.push(point);
        }
      }

      if (uniqueTrendLineData.length > 0) {
        vcpTrendLine.setData(uniqueTrendLineData);
      }

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

    // 6. Combine and Plot Markers
    let allMarkers: any[] = [];

    // A. Generic Backtest Markers (PASS/FAIL)
    if (showMarkers && backtestMarkers && backtestMarkers.length > 0) {
      const mapped = backtestMarkers.map((m: any) => {
        // Ensure date is YYYY-MM-DD string
        // Generic markers use 'time', SEPA uses 'date'. Handle both safely.
        let markerTimeStr = m.time || m.date;
        
        if (markerTimeStr && typeof markerTimeStr === 'string' && markerTimeStr.includes('T')) {
             markerTimeStr = markerTimeStr.split('T')[0];
        }
        
        // Align marker time
        // We need to find the exact string match in formattedData
        // If not found, find the next available date
        let finalTime = markerTimeStr;
        
        const exactMatch = formattedData.find((d) => d.time === markerTimeStr);
        if (!exactMatch) {
             const nextIdx = formattedData.findIndex((d) => d.time > markerTimeStr);
             if (nextIdx !== -1) finalTime = formattedData[nextIdx].time;
             else finalTime = formattedData[formattedData.length - 1].time;
        }

        return {
          time: finalTime,
          position: m.pass ? 'belowBar' : 'aboveBar',
          color: m.pass ? '#ff69b4' : '#ffd54f',
          shape: m.pass ? 'arrowUp' : 'arrowDown',
          text: m.pass ? 'PASS' : 'FAIL',
        };
      });
      allMarkers = [...allMarkers, ...mapped];
    }

    // B. SEPA Backtest Markers (Blue Buy Arrows)
    if (showMarkers && sepaBacktestMarkers && sepaBacktestMarkers.length > 0) {
        const sepaMapped = sepaBacktestMarkers.map((m: any) => {
            // Ensure date is YYYY-MM-DD string
            let markerTimeStr = m.date || m.time;
            
            if (markerTimeStr && typeof markerTimeStr === 'string' && markerTimeStr.includes('T')) {
                markerTimeStr = markerTimeStr.split('T')[0];
            }
            
            // Align marker time
            let finalTime = markerTimeStr;
            
            const exactMatch = formattedData.find((d) => d.time === markerTimeStr);
            if (!exactMatch) {
                const nextIdx = formattedData.findIndex((d) => d.time > markerTimeStr);
                if (nextIdx !== -1) finalTime = formattedData[nextIdx].time;
                else finalTime = formattedData[formattedData.length - 1].time;
            }
            
            return {
                time: finalTime,
                position: 'belowBar',
                color: '#2196F3', // Blue for SEPA Buy
                shape: 'arrowUp',
                text: 'SEPA Buy',
                size: 2,
            }
        });
        allMarkers = [...allMarkers, ...sepaMapped];
    }

    // C. Set All Markers to Chart
    if (allMarkers.length > 0) {
        // Sort by time string
        allMarkers.sort((a: any, b: any) => {
            if (a.time < b.time) return -1;
            if (a.time > b.time) return 1;
            return 0;
        });
        
        // Use createSeriesMarkers helper function as per documentation
        createSeriesMarkers(candlestickSeries, allMarkers);
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
  }, [data, vcpAnalysis, showVCP, backtestMarkers, showMarkers]); // Re-run this effect when markers or toggle change too

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
          {/* Backtest Markers Toggle */}
          <button
            onClick={() => setShowMarkers(!showMarkers)}
            style={{
              position: 'absolute',
              top: '10px',
              left: '90px',
              zIndex: 10,
              padding: '4px 10px',
              backgroundColor: showMarkers ? '#4caf50' : '#666',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '12px',
              fontWeight: '500',
              boxShadow: '0 2px 5px rgba(0,0,0,0.3)',
              transition: 'background-color 0.3s ease',
              marginLeft: '10px'
            }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = showMarkers ? '#45a049' : '#555'; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = showMarkers ? '#4caf50' : '#666'; }}
          >
            {showMarkers ? '✓ Markers' : 'Markers'}
          </button>
        
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
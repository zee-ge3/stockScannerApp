import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer 
} from 'recharts';

interface PriceData {
  date: string;
  close: number;
}

interface Props {
  data: PriceData[];
}

const PriceChart = ({ data }: Props) => {
  // Format data for Recharts (ensure dates are readable strings)
  const chartData = data.map(item => ({
    ...item,
    dateStr: new Date(item.date).toLocaleDateString()
  }));

  // Calculate min/max for Y-Axis scaling so the line doesn't look flat
  const minPrice = Math.min(...data.map(d => d.close));
  const maxPrice = Math.max(...data.map(d => d.close));
  const buffer = (maxPrice - minPrice) * 0.1;

  return (
    <div style={{ width: '100%', height: 300, marginTop: '20px', marginBottom: '20px' }}>
      <ResponsiveContainer>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#8884d8" stopOpacity={0.8}/>
              <stop offset="95%" stopColor="#8884d8" stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
          <XAxis 
            dataKey="dateStr" 
            tick={{ fontSize: 12, fill: '#888' }} 
            minTickGap={50}
          />
          <YAxis 
            domain={[minPrice - buffer, maxPrice + buffer]} 
            tick={{ fontSize: 12, fill: '#888' }}
            tickFormatter={(val) => `$${val.toFixed(0)}`}
          />
          <Tooltip 
            contentStyle={{ backgroundColor: '#333', border: 'none', borderRadius: '5px' }}
            itemStyle={{ color: '#fff' }}
            formatter={(value: number | undefined) => {
              if (value === undefined) return ['N/A', 'Price'];
              return [`$${value.toFixed(2)}`, 'Price'];
            }}
          />
          <Area 
            type="monotone" 
            dataKey="close" 
            stroke="#8884d8" 
            fillOpacity={1} 
            fill="url(#colorPrice)" 
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};

export default PriceChart;
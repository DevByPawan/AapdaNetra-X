import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import type { Forecast } from '../../types';
import { PanelShell, PanelHeader } from '../common/Panel';

interface HazardForecastChartProps {
  forecast: Forecast;
}

export function HazardForecastChart({ forecast }: HazardForecastChartProps) {
  const data = forecast.points.map(p => ({
    name: p.minutesOffset === 0 ? 'NOW' : `+${p.minutesOffset}M`,
    risk: p.risk,
  }));
  const lastPoint = forecast.points[forecast.points.length - 1];

  return (
    <PanelShell className="flex flex-col">
      <PanelHeader
        title="Hazard Forecast"
        sub={`Next ${lastPoint?.minutesOffset ?? 60} minutes`}
      />
      <div className="px-[14px] py-[12px] flex-1">
        <ResponsiveContainer width="100%" height={120}>
          <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
            <defs>
              <linearGradient id="riskGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#ff5d6c" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#ff5d6c" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="name"
              tick={{ fill: '#71869b', fontSize: 8 }}
              tickLine={false}
              axisLine={{ stroke: '#20334a' }}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fill: '#71869b', fontSize: 8 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              contentStyle={{
                background: '#0d1a2b',
                border: '1px solid #21334a',
                borderRadius: 6,
                fontSize: 10,
                color: '#eaf1f8',
              }}
            formatter={(v) => [`${String(v)}%`, 'Risk']}
            />
            <Area
              type="monotone"
              dataKey="risk"
              stroke="#ff6d7a"
              strokeWidth={2.5}
              fill="url(#riskGrad)"
              dot={false}
              activeDot={{ r: 4, fill: '#ff5d6c', stroke: '#fff', strokeWidth: 1 }}
            />
          </AreaChart>
        </ResponsiveContainer>

        <div className="flex justify-between text-ax-muted text-[9px] mt-2">
          <span>
            Risk trend:{' '}
            <b style={{ color: '#ff8791' }}>{forecast.trendLabel}</b>
          </span>
          <span>
            Model confidence:{' '}
            <b style={{ color: '#6fe4b0' }}>{Math.round(forecast.confidence * 100)}%</b>
          </span>
        </div>
      </div>
    </PanelShell>
  );
}

import React, { createContext, useContext } from 'react';

/**
 * Mock leve de recharts para jsdom. Renderiza os filhos e, para exercitar a lógica própria dos
 * componentes, executa `tickFormatter`, `formatter` e `content` (de Tooltip) com dados do gráfico.
 */
const ChartData = createContext<Array<Record<string, unknown>>>([]);

type Anyish = any; // eslint-disable-line @typescript-eslint/no-explicit-any

const Chart = ({ data, children }: Anyish) => (
  <ChartData.Provider value={Array.isArray(data) ? data : []}>
    <div data-testid="chart">{children}</div>
  </ChartData.Provider>
);
const Pass = ({ children }: Anyish) => <div>{children}</div>;
const Leaf = () => <div />;
const RefArea = ({ x1, x2 }: Anyish) => <span data-testid="ref-area" data-x1={x1} data-x2={x2} />;

const Axis = ({ tickFormatter, dataKey }: Anyish) => {
  const rows = useContext(ChartData);
  if (typeof tickFormatter !== 'function') return <div />;
  const sample = dataKey && rows[0] ? rows[0][dataKey] : 1500000;
  return <span data-testid="axis-tick">{String(tickFormatter(sample, 0))}</span>;
};

const Tooltip = ({ formatter, content, labelFormatter }: Anyish) => {
  const rows = useContext(ChartData);
  const first = rows[0];
  if (React.isValidElement(content)) {
    return (
      <div data-testid="tooltip-content">
        {React.cloneElement(content as React.ReactElement<Anyish>, { active: true, payload: first ? [{ payload: first }] : [], label: first?.ano ?? 'x' })}
      </div>
    );
  }
  if (typeof content === 'function') {
    return <div data-testid="tooltip-content">{content({ active: true, payload: first ? [{ payload: first }] : [], label: 'x' })}</div>;
  }
  if (typeof formatter === 'function') {
    const out = formatter(1500, 'Salário Mínimo (BRL)', {}, 0, []);
    return <span data-testid="tooltip-fmt">{Array.isArray(out) ? out.join('|') : String(out)}</span>;
  }
  if (typeof labelFormatter === 'function') return <span data-testid="tooltip-label">{String(labelFormatter('x'))}</span>;
  return <div />;
};

export const rechartsMock = {
  ResponsiveContainer: Pass,
  BarChart: Chart,
  LineChart: Chart,
  AreaChart: Chart,
  ComposedChart: Chart,
  PieChart: Chart,
  RadarChart: Chart,
  Bar: Pass,
  Line: Leaf,
  Area: Leaf,
  Pie: Pass,
  Cell: Leaf,
  XAxis: Axis,
  YAxis: Axis,
  CartesianGrid: Leaf,
  Tooltip,
  Legend: Leaf,
  ReferenceLine: Leaf,
  ReferenceArea: RefArea,
  LabelList: Leaf,
  Radar: Leaf,
  PolarGrid: Leaf,
  PolarAngleAxis: Leaf,
  PolarRadiusAxis: Leaf,
};

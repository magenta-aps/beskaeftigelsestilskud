const renderGraph = function (selector, data, yearlyIncome, yearlyBenefit) {
    const graph = $(selector);

    if (yearlyIncome > data[data.length - 1][0]) {
        // result is greater than our current max point in the graph
        data = [...data, [yearlyIncome, 0]];  // Clone array
    }

    let chartData = {
        "chart": {
            "nonce": "{{ request.csp_nonce }}",
            "type": "line",
            "toolbar": {"show": false},
            "animations": {"enabled": false},
            "selection": {"enabled": false},
            "fontFamily": "Figtree Normal, Trebuchet MS, Helvetica, sans-serif",
            "height": "100%",
        },
        "tooltip": {"enabled": false},
        "colors": ["#820041"], // $primary
        "series": [
            {
                "name": "Suila",
                "data": data,
            },
        ],
        "grid": {
            "padding": {
                "top": 50,
                "right": 200,
                "bottom": 50,
                "left": 50,
            },
        },
        "markers": {
            "size": 7,
            "strokeWidth": 0,
            "colors": ["#820041"], // $primary
        },
        "dataLabels": {
            "enabled": true,
            "textAnchor": "middle",
            "offsetY": -35,
            "formatter": function (val, opts) {
                if (opts.dataPointIndex === 0) {
                    return
                }

                const benefit = val;
                const income = data[opts.dataPointIndex][0];
                return [
                    `Årsindkomst: ${income} kr`,
                    `Suila-tapit: ${benefit} kr.`,
                ]
            },
            "style": {
                "fontSize": "17px",
                "fontWeight": "normal",
                "colors": ["#bf0169"], // $light-secondary
            },
            "background": {
                "padding": 30,
                "borderRadius": 10,
            }
        },
        "legend": {
            "fontSize": "17px",
            "color": "#820041", // $primary
        },
        "xaxis": {
            "type": "numeric",
            "title": {
                "text": gettext("Årsindkomst i kr."),
                "style": {
                    "fontSize": "17px",
                    "color": "#820041", // $primary
                },
            },
            "labels": {
                "style": {
                    "fontSize": "17px",
                    "colors": ["#820041"], // $primary
                },
                "offsetY": -2,
            },
        },
        "yaxis": {
            "title": {
                "text": gettext("Suila-tapit i kr."),
                "style": {
                    "fontSize": "17px",
                    "color": "#820041", // $primary
                },
            },
            "labels": {
                "style": {
                    "fontSize": "17px",
                    "colors": ["#820041"], // $primary
                }
            },
        },
    };

    if (!isNaN(yearlyIncome) && !isNaN(yearlyBenefit)) {
        chartData["annotations"] = {
            "points": [{
                "x": yearlyIncome,
                "y": yearlyBenefit,
                "marker": {
                    "size": 4,
                },
                "label": {
                    "text": [
                        gettext("Årsindkomst: ") + yearlyIncome,
                        gettext("Suila-tapit: ") + yearlyBenefit,
                    ],
                    "style": {
                        "background": "#ffe169", // $secondary
                        "color": "#820041", // $primary
                        "fontSize": "17px",
                    },
                    "borderColor": "#ffe169", // $secondary
                    "borderWidth": 20,
                    "borderRadius": 5,
                }
            }]
        }
    }

    const chart = new ApexCharts(graph.get(0), chartData);
    chart.render();
}

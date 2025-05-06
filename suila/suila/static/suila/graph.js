/*
SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
SPDX-License-Identifier: MPL-2.0
*/
/* eslint-env jquery */
/* global $ */
const renderGraph = function (selector, data, yearlyIncome, yearlyBenefit) {
    const graph = $(selector);
    const formatter = new Intl.NumberFormat(
        "da-DK",
        {
            style: "currency",
            currency: "DKK",
            maximumFractionDigits: 0,
        }
    );
    const breakpointMD = 768;

    if (yearlyIncome > data[data.length - 1][0]) {
        // result is greater than our current max point in the graph
        data = [...data, [yearlyIncome, 0]];  // Clone array, and put point at the end
    }
    const monthlyBenefit = (!isNaN(yearlyIncome) && !isNaN(yearlyBenefit)) ? Math.ceil(yearlyBenefit / 12) : null;

    // Using ApexCharts' `responsive` features has proven shaky at best, resulting in
    // options from one breakpoint bleeding into another on resize.
    // Therefore, we instead define a complete set of options for each breakpoint,
    // and apply the whole thing on resize.
    const chartData = [
        {
            "size": {
                "gt": breakpointMD,
                "lt": null,
            },
            "options": {
                "chart": {
                    "nonce": "{{ request.csp_nonce }}",
                    "type": "line",
                    "toolbar": {"show": false},
                    "animations": {"enabled": false},
                    "selection": {"enabled": false},
                    "fontFamily": "Figtree Normal, Trebuchet MS, Helvetica, sans-serif",
                    "height": "100%",
                    "width": "100%",
                    "redrawOnParentResize": true,
                    "redrawOnWindowResize": true,
                    "zoom": {
                        "allowMouseWheelZoom": false,
                    }
                },
                "tooltip": {"enabled": false},
                "colors": ["#820041"], // $primary
                "series": [
                    {
                        "name": gettext("Suila-tapit"),
                        "data": data,
                    },
                ],
                "grid": {
                    "padding": {
                        "top": 50,
                        "right": 150,
                        "bottom": 10,
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
                        const x = data[opts.dataPointIndex][0]
                        if (x === yearlyIncome) {
                            return []  // No label if point matches real income point
                            // (to avoid two labels at the same coordinates)
                        }
                        const pointYearlyIncome = formatter.format(x);
                        const pointMonthlyBenefit = formatter.format(Math.ceil(val / 12));
                        return [
                            interpolate(gettext("Årsindkomst: %s"), [pointYearlyIncome]),
                            interpolate(gettext("Suila-tapit: %s"), [pointMonthlyBenefit]),
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
                "stroke": {
                    "show": true,
                    "width": 5,
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
                        "formatter": formatter.format,
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
                        },
                        "formatter": formatter.format,
                    },
                },
                "annotations": monthlyBenefit !== null ? {
                    "points": [{
                        "x": yearlyIncome,
                        "y": yearlyBenefit,
                        "marker": {
                            "size": 4,
                        },
                        "label": {
                            "text": [
                                interpolate(gettext("Årsindkomst: %s"), [formatter.format(yearlyIncome)]),
                                interpolate(gettext("Suila-tapit: %s"), [formatter.format(monthlyBenefit)]),
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
                } : {},
            }
        },
        {
            "size": {
                "gt": null,
                "lt": breakpointMD,
            },
            "options": {
                "chart": {
                    "nonce": "{{ request.csp_nonce }}",
                    "type": "line",
                    "toolbar": {"show": false},
                    "animations": {"enabled": false},
                    "selection": {"enabled": false},
                    "fontFamily": "Figtree Normal, Trebuchet MS, Helvetica, sans-serif",
                    "height": "100%",
                    "width": "100%",
                    "redrawOnParentResize": true,
                    "redrawOnWindowResize": true,
                    "zoom": {
                        "allowMouseWheelZoom": false,
                    }
                },
                "tooltip": {"enabled": false},
                "colors": ["#820041"], // $primary
                "series": [
                    {
                        "name": gettext("Suila-tapit"),
                        "data": data,
                    },
                ],
                "grid": {
                    "padding": {
                        "top": 10,
                        "right": 10,
                        "bottom": 10,
                        "left": 10,
                    },
                },
                "markers": {
                    "size": 4,
                    "strokeWidth": 0,
                    "colors": ["#820041"], // $primary
                },
                "dataLabels": {
                    "enabled": false,
                },

                "legend": {
                    "fontSize": "12px",
                    "color": "#820041", // $primary
                },
                "stroke": {
                    "show": true,
                    "width": 2,
                },
                "xaxis": {
                    "type": "numeric",
                    "title": {
                        "text": gettext("Årsindkomst i kr."),
                        "style": {
                            "fontSize": "12px",
                            "color": "#820041", // $primary
                        },
                    },
                    "labels": {
                        "style": {
                            "fontSize": "12px",
                            "colors": ["#820041"], // $primary
                        },
                        "offsetY": -2,
                        "formatter": formatter.format,
                    },
                },
                "yaxis": {
                    "title": {
                        "text": gettext("Suila-tapit i kr."),
                        "style": {
                            "fontSize": "12px",
                            "color": "#820041", // $primary
                        },
                    },
                    "labels": {
                        "style": {
                            "fontSize": "12px",
                            "colors": ["#820041"], // $primary
                        },
                        "formatter": formatter.format,
                    },
                },
                "annotations": monthlyBenefit !== null ? {
                    "points": [{
                        "x": yearlyIncome,
                        "y": yearlyBenefit,
                        "marker": {
                            "size": 4,
                            "fillColor": "#ffe169",
                            "strokeColor": "#820041",
                            "strokeWidth": 1,
                        },
                        "label": {
                            "text": [
                                interpolate(gettext("Årsindkomst: %s"), [formatter.format(yearlyIncome)]),
                                interpolate(gettext("Suila-tapit: %s"), [formatter.format(monthlyBenefit)]),
                            ],
                            "style": {
                                "background": "#ffe169", // $secondary
                                "color": "#820041", // $primary
                                "fontSize": "12px",
                            },
                            "borderColor": "#ffe169", // $secondary
                            "borderWidth": 20,
                            "borderRadius": 5,
                            "offsetY": -25,
                        }
                    }],
                } : {},
            }
        }
    ];

    const getChartOptionsForBreakpoint = function () {
        const windowWidth = window.innerWidth;
        for (let chart of chartData) {
            const size = chart["size"];
            if (
                (size["lt"] === null || windowWidth < size["lt"]) &&
                (size["gt"] === null || windowWidth >= size["gt"])
            ) {
                return chart;
            }
        }
        return chart[0];
    }

    let currentChart = getChartOptionsForBreakpoint();
    const chart = new ApexCharts(graph.get(0), currentChart["options"]);

    const updateBreakpoint = function() {
        const newChart = getChartOptionsForBreakpoint();
        if (newChart !== currentChart) {
            chart.updateOptions(newChart["options"], true, true);
            currentChart = newChart;
        }
    }

    chart.render();
    window.addEventListener('resize', updateBreakpoint);
}

<?php

# Her opsættes demobrugere og deres data


$config = array(
    'admin' => array(
        'core:AdminPassword',''
    ),
    'example-userpass' => array(
        'exampleauth:UserPass',
        
        'indberetter:indberetter' => array(
            # Claims fra OIOSAML
            'https://data.gov.dk/model/core/specVersion' => 'OIO-SAML-3.0',
            'https://data.gov.dk/concept/core/nsis/loa' => 'Substantial',
            'https://data.gov.dk/concept/core/nsis/ial' => 'Substantial',
            'https://data.gov.dk/concept/core/nsis/aal' => 'High',
            'https://data.gov.dk/model/core/eid/fullName' => 'Anders And',
            'https://data.gov.dk/model/core/eid/firstName' => 'Anders',
            'https://data.gov.dk/model/core/eid/lastName' => 'And',
            'https://data.gov.dk/model/core/eid/email' => 'anders@andeby.dk',
            'https://data.gov.dk/model/core/eid/cprNumber' => '0111111111',
            'https://data.gov.dk/model/core/eid/age' => '60',
            'https://data.gov.dk/model/core/eid/cprUuid' => 'urn:uuid:323e4567-e89b-12d3-a456-426655440000',
            'https://data.gov.dk/model/core/eid/professional/cvr' => '12345678',
            'https://data.gov.dk/model/core/eid/professional/orgName' => 'Joakim von Ands pengetank',
            'https://data.gov.dk/model/core/eid/privilegesIntermediate' =>
                'PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4KPGJwcDpQcml2aWxlZ2VMaXN0
                CnhtbG5zOmJwcD0iaHR0cDovL2l0c3QuZGsvb2lvc2FtbC9iYXNpY19wcml2aWxlZ2VfcHJvZmls
                ZSIKeG1sbnM6eHNpPSJodHRwOi8vd3d3LnczLm9yZy8yMDAxL1hNTFNjaGVtYS1pbnN0YW5jZSIg
                Pgo8UHJpdmlsZWdlR3JvdXAgU2NvcGU9InVybjpkazpnb3Y6c2FtbDpjdnJOdW1iZXJJZGVudGlm
                aWVyOjEyMzQ1Njc4Ij4KPFByaXZpbGVnZT51cm46ZGs6c29tZV9kb21haW46bXlQcml2aWxlZ2Ux
                QTwvUHJpdmlsZWdlPgo8UHJpdmlsZWdlPnVybjpkazpzb21lX2RvbWFpbjpteVByaXZpbGVnZTFC
                PC9Qcml2aWxlZ2U+CjwvUHJpdmlsZWdlR3JvdXA+CjxQcml2aWxlZ2VHcm91cCBTY29wZT0idXJu
                OmRrOmdvdjpzYW1sOnNlTnVtYmVySWRlbnRpZmllcjoyNzM4NDIyMyI+CjxQcml2aWxlZ2U+dXJu
                OmRrOnNvbWVfZG9tYWluOm15UHJpdmlsZWdlMUM8L1ByaXZpbGVnZT4KPFByaXZpbGVnZT51cm46
                ZGs6c29tZV9kb21haW46bXlQcml2aWxlZ2UxRDwvUHJpdmlsZWdlPgo8L1ByaXZpbGVnZUdyb3Vw
                Pgo8L2JwcDpQcml2aWxlZ2VMaXN0Pgo='
        ),

        'indberetter2:indberetter2' => array(
            # Claims fra OIOSAML
            'https://data.gov.dk/model/core/specVersion' => 'OIO-SAML-3.0',
            'https://data.gov.dk/concept/core/nsis/loa' => 'Substantial',
            'https://data.gov.dk/concept/core/nsis/ial' => 'Substantial',
            'https://data.gov.dk/concept/core/nsis/aal' => 'High',
            'https://data.gov.dk/model/core/eid/fullName' => 'Mickey Mouse',
            'https://data.gov.dk/model/core/eid/firstName' => 'Mickey',
            'https://data.gov.dk/model/core/eid/lastName' => 'Mouse',
            'https://data.gov.dk/model/core/eid/email' => 'mickey@andeby.dk',
            'https://data.gov.dk/model/core/eid/cprNumber' => '2222222222',
            'https://data.gov.dk/model/core/eid/age' => '60',
            'https://data.gov.dk/model/core/eid/cprUuid' => 'urn:uuid:323e4567-e89b-12d3-a456-426655440000',
            'https://data.gov.dk/model/core/eid/professional/cvr' => '12345679',
            'https://data.gov.dk/model/core/eid/professional/orgName' => 'Joakim von Ands pengetank',
            'https://data.gov.dk/model/core/eid/privilegesIntermediate' =>
                'PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4KPGJwcDpQcml2aWxlZ2VMaXN0
                CnhtbG5zOmJwcD0iaHR0cDovL2l0c3QuZGsvb2lvc2FtbC9iYXNpY19wcml2aWxlZ2VfcHJvZmls
                ZSIKeG1sbnM6eHNpPSJodHRwOi8vd3d3LnczLm9yZy8yMDAxL1hNTFNjaGVtYS1pbnN0YW5jZSIg
                Pgo8UHJpdmlsZWdlR3JvdXAgU2NvcGU9InVybjpkazpnb3Y6c2FtbDpjdnJOdW1iZXJJZGVudGlm
                aWVyOjEyMzQ1Njc4Ij4KPFByaXZpbGVnZT51cm46ZGs6c29tZV9kb21haW46bXlQcml2aWxlZ2Ux
                QTwvUHJpdmlsZWdlPgo8UHJpdmlsZWdlPnVybjpkazpzb21lX2RvbWFpbjpteVByaXZpbGVnZTFC
                PC9Qcml2aWxlZ2U+CjwvUHJpdmlsZWdlR3JvdXA+CjxQcml2aWxlZ2VHcm91cCBTY29wZT0idXJu
                OmRrOmdvdjpzYW1sOnNlTnVtYmVySWRlbnRpZmllcjoyNzM4NDIyMyI+CjxQcml2aWxlZ2U+dXJu
                OmRrOnNvbWVfZG9tYWluOm15UHJpdmlsZWdlMUM8L1ByaXZpbGVnZT4KPFByaXZpbGVnZT51cm46
                ZGs6c29tZV9kb21haW46bXlQcml2aWxlZ2UxRDwvUHJpdmlsZWdlPgo8L1ByaXZpbGVnZUdyb3Vw
                Pgo8L2JwcDpQcml2aWxlZ2VMaXN0Pgo='
        ),
        'indberetter3:indberetter3' => array(
            # Claims fra OIOSAML
            'https://data.gov.dk/model/core/specVersion' => 'OIO-SAML-3.0',
            'https://data.gov.dk/concept/core/nsis/loa' => 'Substantial',
            'https://data.gov.dk/concept/core/nsis/ial' => 'Substantial',
            'https://data.gov.dk/concept/core/nsis/aal' => 'High',
            'https://data.gov.dk/model/core/eid/fullName' => 'Fedtmule',
            'https://data.gov.dk/model/core/eid/firstName' => 'Fedtmule',
            'https://data.gov.dk/model/core/eid/lastName' => '',
            'https://data.gov.dk/model/core/eid/email' => 'fedtmule@andeby.dk',
            'https://data.gov.dk/model/core/eid/cprNumber' => '3333333333',
            'https://data.gov.dk/model/core/eid/age' => '60',
            'https://data.gov.dk/model/core/eid/cprUuid' => 'urn:uuid:323e4567-e89b-12d3-a456-426655440000',
            'https://data.gov.dk/model/core/eid/professional/orgName' => 'Arbejdsløs',
            'https://data.gov.dk/model/core/eid/privilegesIntermediate' =>
                'PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4KPGJwcDpQcml2aWxlZ2VMaXN0
                        CnhtbG5zOmJwcD0iaHR0cDovL2l0c3QuZGsvb2lvc2FtbC9iYXNpY19wcml2aWxlZ2VfcHJvZmls
                        ZSIKeG1sbnM6eHNpPSJodHRwOi8vd3d3LnczLm9yZy8yMDAxL1hNTFNjaGVtYS1pbnN0YW5jZSIg
                        Pgo8UHJpdmlsZWdlR3JvdXAgU2NvcGU9InVybjpkazpnb3Y6c2FtbDpjdnJOdW1iZXJJZGVudGlm
                        aWVyOjEyMzQ1Njc4Ij4KPFByaXZpbGVnZT51cm46ZGs6c29tZV9kb21haW46bXlQcml2aWxlZ2Ux
                        QTwvUHJpdmlsZWdlPgo8UHJpdmlsZWdlPnVybjpkazpzb21lX2RvbWFpbjpteVByaXZpbGVnZTFC
                        PC9Qcml2aWxlZ2U+CjwvUHJpdmlsZWdlR3JvdXA+CjxQcml2aWxlZ2VHcm91cCBTY29wZT0idXJu
                        OmRrOmdvdjpzYW1sOnNlTnVtYmVySWRlbnRpZmllcjoyNzM4NDIyMyI+CjxQcml2aWxlZ2U+dXJu
                        OmRrOnNvbWVfZG9tYWluOm15UHJpdmlsZWdlMUM8L1ByaXZpbGVnZT4KPFByaXZpbGVnZT51cm46
                        ZGs6c29tZV9kb21haW46bXlQcml2aWxlZ2UxRDwvUHJpdmlsZWdlPgo8L1ByaXZpbGVnZUdyb3Vw
                        Pgo8L2JwcDpQcml2aWxlZ2VMaXN0Pgo='
        ),
        'indberetter4:indberetter4' => array(
            # Claims fra OIOSAML
            'https://data.gov.dk/model/core/specVersion' => 'OIO-SAML-3.0',
            'https://data.gov.dk/concept/core/nsis/loa' => 'Substantial',
            'https://data.gov.dk/concept/core/nsis/ial' => 'Substantial',
            'https://data.gov.dk/concept/core/nsis/aal' => 'High',
            'https://data.gov.dk/model/core/eid/fullName' => 'Rip And',
            'https://data.gov.dk/model/core/eid/firstName' => 'Rip',
            'https://data.gov.dk/model/core/eid/lastName' => '',
            'https://data.gov.dk/model/core/eid/email' => 'rip@andeby.dk',
            'https://data.gov.dk/model/core/eid/cprNumber' => '4444444444',
            'https://data.gov.dk/model/core/eid/age' => '60',
            'https://data.gov.dk/model/core/eid/cprUuid' => 'urn:uuid:323e4567-e89b-12d3-a456-426655440000',
            'https://data.gov.dk/model/core/eid/professional/orgName' => 'Arbejdsløs',
            'https://data.gov.dk/model/core/eid/privilegesIntermediate' =>
                'PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4KPGJwcDpQcml2aWxlZ2VMaXN0
                        CnhtbG5zOmJwcD0iaHR0cDovL2l0c3QuZGsvb2lvc2FtbC9iYXNpY19wcml2aWxlZ2VfcHJvZmls
                        ZSIKeG1sbnM6eHNpPSJodHRwOi8vd3d3LnczLm9yZy8yMDAxL1hNTFNjaGVtYS1pbnN0YW5jZSIg
                        Pgo8UHJpdmlsZWdlR3JvdXAgU2NvcGU9InVybjpkazpnb3Y6c2FtbDpjdnJOdW1iZXJJZGVudGlm
                        aWVyOjEyMzQ1Njc4Ij4KPFByaXZpbGVnZT51cm46ZGs6c29tZV9kb21haW46bXlQcml2aWxlZ2Ux
                        QTwvUHJpdmlsZWdlPgo8UHJpdmlsZWdlPnVybjpkazpzb21lX2RvbWFpbjpteVByaXZpbGVnZTFC
                        PC9Qcml2aWxlZ2U+CjwvUHJpdmlsZWdlR3JvdXA+CjxQcml2aWxlZ2VHcm91cCBTY29wZT0idXJu
                        OmRrOmdvdjpzYW1sOnNlTnVtYmVySWRlbnRpZmllcjoyNzM4NDIyMyI+CjxQcml2aWxlZ2U+dXJu
                        OmRrOnNvbWVfZG9tYWluOm15UHJpdmlsZWdlMUM8L1ByaXZpbGVnZT4KPFByaXZpbGVnZT51cm46
                        ZGs6c29tZV9kb21haW46bXlQcml2aWxlZ2UxRDwvUHJpdmlsZWdlPgo8L1ByaXZpbGVnZUdyb3Vw
                        Pgo8L2JwcDpQcml2aWxlZ2VMaXN0Pgo='
        )
    )
);

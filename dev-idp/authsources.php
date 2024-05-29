<?php

# Her opsættes demobrugere og deres data


$config = array(
    'admin' => array(
        'core:AdminPassword',''
    ),
    'example-userpass' => array(
        'exampleauth:UserPass',
        
        'borger:borger' => array(
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

    )
);

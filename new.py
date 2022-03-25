#============================== Calling all the Libraries=====================================
from flask import Flask
from flask_restful import Api, Resource, reqparse
import pandas as pd
import operator as op
import numpy as np
import requests
import calendar
import datetime
calendar.setfirstweekday(0)
import warnings
import matplotlib.pyplot as plt
warnings.filterwarnings('ignore')



pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
#============================== END: Calling all the Libraries=====================================

global setCookieP44
setCookieP44=None

# ===========================================================================
# Name: loginP44
# Functionality: Use P44 credentials to login and get the Authorization code in set-cookie
# Params: No Params
# Response: Returns the set-Cookie that contains Authorization code for further interaction with P44
# ===========================================================================
def loginP44():
    P44_USERNAME="drew@synchrogistics.com"
    P44_PASSWORD="Synchro2022!"
    p44_login_url = 'https://na12.api.project44.com/api/portal/v2/login'

    payload = {"username":P44_USERNAME,"password":P44_PASSWORD}
    global setCookieP44
    with requests.session() as s:
        response_post = s.post(p44_login_url, json=payload)
        if 'Set-Cookie' in response_post.headers:
            setCookieP44=response_post.headers['Set-Cookie']
    return setCookieP44


# ===========================================================================
# Name: p44Rates
# Functionality: Interact with P44 to get the quotation rates. 
# Params: Origin Zip, Destination Zip, Customer Code, Weight, Freight Class, Pallet
# Response: Returns the filtered response dict for the client, and source dict to store in the database 
# Notes: Needs to be changed in future to incorporate accessorials/dimensions
# ===========================================================================
def p44Rates(originZip,destZip,customerCode,weight,freightClass,pallet):
    global setCookieP44
    if setCookieP44==None:
        setCookieP44=loginP44()
    p44_quote_url = 'https://na12.api.project44.com/rate/quote'

    payloadQuote = {"accessorials":[],
               "origin":{"postalCode":f"{originZip}"},
    #            "shipDate":"1647950459644",
               "destination":{"postalCode":f"{destZip}"},
               "mode":"LTL",
               "loginGroupKey":f"{customerCode}",
               "lineItems":[{"qty":1,
#                              "length":"10",
#                              "width":"10",
#                              "height":"10",
                             "weight":f"{weight}",
                             "freightClass":f"{freightClass}",
                             "nmfcSub":"",
                             "nmfcItem":"",
                             "description":"LTL Freight",
                             "dimUnit":"in",
                             "weightUnit":"lbs",
                             "stackable":False,
                             "hazmat":False,
                             "pieces":pallet,
                             "packageType":"PLT"}]}
    header={
        'cookie':setCookieP44
    }
    global authorization
    with requests.session() as s:
        response_post = s.post(p44_quote_url, json=payloadQuote, headers=header)
        status=response_post.status_code
        try:
            response=response_post.json()
        except:
            response='Internal Server Error: An internal error has occurred.'
            return response, str(response_post.content)
        carrierDf=pd.DataFrame()
        for i in response['response']:
            tempDf=pd.DataFrame()
            if len(i['errors'])==0:
                tempDf.at[0,'P44 Quote Id']=i['p44QuoteId']
                tempDf.at[0,'Quote Number']=i['quoteNumber']
                tempDf.at[0,'Mode']=i['mode']
                tempDf.at[0,'Origin City']=i['origin']['city']
                tempDf.at[0,'Origin State']=i['origin']['stateName']
                tempDf.at[0,'Origin Zip']=i['origin']['postalCode']
                tempDf.at[0,'Destination City']=i['destination']['city']
                tempDf.at[0,'Destination State']=i['destination']['stateName']
                tempDf.at[0,'Destination Zip']=i['destination']['postalCode']
                tempDf.at[0,'Total Weight']=i['totalWeight']
                tempDf.at[0,'Carrier Id']=i['carrier']['vendorId']
                tempDf.at[0,'Carrier Name']=i['carrier']['displayName']
                costDetail={}
                for j in i['rateDetail']['rateAdjustments']:
                    costDetail[j['description']]=j['amount']
                tempDf.at[0,'Cost Detail']=f"{costDetail}"
                tempDf.at[0,'Total Cost']=i['rateDetail']['total']
                tempDf.at[0,'Price Unit']=i['rateDetail']['currency']
                tempDf.at[0,'Transit Days']=i['rateDetail']['transitTime']
                carrierDf=carrierDf.append(tempDf)
        carrierDf=carrierDf.reset_index(drop=True)
    return {'response' : carrierDf.to_dict('records')}, str(response_post.content)


# ===========================================================================
# Name: writeData
# Functionality: Write the trasaction data in the Excel File
# Params: Request Arguments, Response Status Code, Customer Response, Source Response
# Response: No Response
# ===========================================================================
def writeData(args,statusCode,response, sourceResponse):
    requestDf=pd.read_csv('connectionRequests.csv')
    tempDf=pd.DataFrame()
    tempDf.at[0,'Timestamp']=datetime.datetime.now()
    tempDf.at[0,'Status']=statusCode
    tempDf.at[0,'Params']=str(args)
    tempDf.at[0,'ResponseCustomer']=response
    tempDf.at[0,'ResponseP44']=sourceResponse
    requestDf=requestDf.append(tempDf)
    requestDf.to_csv("connectionRequests.csv",index=False)

# ===========================================================================
# Name: getp44Code
# Functionality: Get the Comapny's p44 Code on the basis of userId/AuthorizationCode/unique Customer Id
# Params: userId/AuthorizationCode/unique Customer Id
# Response: p44 Customer Code
# ===========================================================================
def getp44Code(authCode):
    data = pd.read_csv('users.csv')
    newDf=data[data['authCode']==authCode].reset_index(drop=True)
    if len(newDf)>0:
        response=newDf.at[0,'p44Code']
    else:
        response="Error"
    return response

# ===========================================================================
# Name: getAuthCode
# Functionality: Get the Comapny's uniqueId on the basis of Username/Password
# Params: userName, password
# Response: Comapny's uniqueId
# ===========================================================================
def getAuthCode(userName, password):
    data = pd.read_csv('users.csv')
    newDf=data[(data['loginUserName']==userName) & (data['loginPassword']==password)]
    if len(newDf)>0:
        response=str(newDf.at[0,'authCode'])
    else:
        response="Error: Credentials does not match"
    return response


# ===========================================================================
# API Name: Login
# Functionality: For Login aunthentication and provide uniqueId for further interactions with the API
# Note: Currently the Authorization Code is a constant value, but we would require a changing/dynamic unique id that changes periodically
# ===========================================================================
class Login(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('username', required=True)
        parser.add_argument('password', required=True)
        args = parser.parse_args()

        authCode=getAuthCode(args['username'], args['password'])
        if 'Error' in authCode:
            response= {'status':'Error', 'data':authCode}
            statusCode=415
        else:
            response= {'status':'SUCCESS', 'data':{'authCode':authCode}}
            statusCode=200
        return response, statusCode

# ===========================================================================
# API Name: P44
# Functionality: For fetching quotes from P44 API
# Note: Currently the params are only the REQUIRED varibales that is needed to fetch quotes. In future we need to add dimensions/Accessorials information
# ===========================================================================   
class P44(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('originZip', required=True)
        parser.add_argument('destZip', required=True)
        parser.add_argument('weight', required=True)
        parser.add_argument('freightClass', required=True)
        parser.add_argument('palletCount', required=True)
        parser.add_argument('authCode', required=True)
        args = parser.parse_args()
        p44Code=getp44Code(args['authCode'])
        if p44Code!='Error':
            response, sourceResponse=p44Rates(args['originZip'],args['destZip'],p44Code,args['weight'],args['freightClass'],args['palletCount'])
        else:
            response='Error: Invalid Authorization Code'
        if 'Error' in response:
            statusCode=415
        else:
            statusCode=201
            sourceResponse="No Error"
        writeData(args,statusCode,str(response), str(sourceResponse))
        return response, statusCode

#====================== Call Flask and run the API Application ==========================================

app = Flask(__name__)
api = Api(app)
# Add URL endpoints
api.add_resource(Login, '/api/login')
api.add_resource(P44, '/api/p44Quote')

if __name__ == '__main__':
    
    app.run(host = "0.0.0.0")

#====================== End: Call Flask and run the API Application ==========================================
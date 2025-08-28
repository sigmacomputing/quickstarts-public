import { NextResponse } from 'next/server';
import axios from 'axios';

// Base resource fetching function
async function fetchWithAuth(endpoint: string, token: string) {
  try {
    const baseURL = process.env.SIGMA_BASE_URL || 'https://aws-api.sigmacomputing.com/v2';
    const url = `${baseURL}${endpoint}`;
    console.log(`Fetching: ${url}`);
    const response = await axios.get(url, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/json'
      }
    });
    console.log(`Response status for ${endpoint}:`, response.status);
    return response.data;
  } catch (error) {
    console.error(`Error fetching ${endpoint}:`, (error as any).response?.data || (error as any).message);
    throw error;
  }
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const type = searchParams.get('type');
    const token = searchParams.get('token');

    if (!token) {
      return NextResponse.json(
        { error: 'Authentication token is required' },
        { status: 401 }
      );
    }

    if (!type) {
      return NextResponse.json(
        { error: 'Resource type is required. Use: teams, members, workbooks, connections, workspaces, bookmarks, templates, datasets, dataModels, accountTypes, workbookElements, materializationSchedules' },
        { status: 400 }
      );
    }

    let data: any;
    let transformedData: any[];

    switch (type) {
      case 'teams':
        data = await fetchWithAuth('/teams', token);
        transformedData = (data.entries || data).map((team: any) => ({
          id: team.teamId,
          name: team.name,
          description: team.description || '',
          memberCount: team.memberCount || 0
        }));
        break;

      case 'members':
        data = await fetchWithAuth('/members', token);
        // Filter out potentially inactive members and map to display format
        const activeMembers = (data.entries || data).filter((member: any) => {
          // Add filters for inactive members based on patterns you identify
          // For now, keeping all members - you can modify this filter
          return true;
        });
        
        transformedData = activeMembers.map((member: any) => ({
          id: member.memberId,
          name: `${member.firstName} ${member.lastName}`.trim(),
          email: member.email,
          firstName: member.firstName,
          lastName: member.lastName,
          type: member.memberType
        }));
        break;

      case 'workbooks':
        data = await fetchWithAuth('/workbooks', token);
        transformedData = (data.entries || data).map((workbook: any) => ({
          id: workbook.workbookId,
          name: workbook.name,
          path: workbook.path,
          ownerId: workbook.ownerId,
          createdBy: workbook.createdBy,
          url: workbook.url
        }));
        break;

      case 'connections':
        data = await fetchWithAuth('/connections', token);
        transformedData = (data.entries || data).map((connection: any) => ({
          id: connection.connectionId,
          name: connection.name,
          type: connection.type,
          description: connection.description || ''
        }));
        break;

      case 'workspaces':
        data = await fetchWithAuth('/workspaces', token);
        transformedData = (data.entries || data).map((workspace: any) => ({
          id: workspace.workspaceId,
          name: workspace.name,
          description: workspace.description || ''
        }));
        break;

      case 'bookmarks':
        // Using favorites endpoint since bookmarks API maps to favorites
        data = await fetchWithAuth('/favorites', token);
        transformedData = (data.entries || data).map((favorite: any) => ({
          id: favorite.favoriteId || favorite.inodeId,
          name: favorite.name || favorite.title,
          description: favorite.description || '',
          type: favorite.type || 'favorite',
          url: favorite.url
        }));
        break;

      case 'templates':
        data = await fetchWithAuth('/templates', token);
        transformedData = (data.entries || data).map((template: any) => ({
          id: template.templateId,
          name: template.name,
          description: template.description || '',
          type: template.type
        }));
        break;

      case 'datasets':
        data = await fetchWithAuth('/datasets', token);
        transformedData = (data.entries || data).map((dataset: any) => ({
          id: dataset.datasetId,
          name: dataset.name,
          description: dataset.description || '',
          type: dataset.type
        }));
        break;

      case 'dataModels':
        data = await fetchWithAuth('/dataModels', token);
        transformedData = (data.entries || data).map((dataModel: any) => ({
          id: dataModel.dataModelId,
          name: dataModel.name,
          description: dataModel.description || '',
          type: dataModel.type || 'dataModel'
        }));
        break;

      case 'accountTypes':
        data = await fetchWithAuth('/accountTypes', token);
        console.log('AccountTypes raw data:', JSON.stringify(data, null, 2));
        transformedData = (data.entries || data).map((accountType: any) => ({
          id: accountType.accountTypeName,
          name: accountType.accountTypeName,
          description: accountType.description || '',
          type: accountType.isCustom ? 'custom' : 'built-in',
          isCustom: accountType.isCustom
        }));
        break;

      case 'workbookElements':
        const workbookId = searchParams.get('workbookId');
        if (!workbookId) {
          return NextResponse.json(
            { error: 'workbookId parameter is required for workbookElements' },
            { status: 400 }
          );
        }
        
        try {
          // First, get all pages from the workbook
          console.log(`Fetching pages for workbook: ${workbookId}`);
          const pagesData = await fetchWithAuth(`/workbooks/${workbookId}/pages`, token);
          console.log('Pages data:', JSON.stringify(pagesData, null, 2));
          
          const pages = pagesData.entries || pagesData || [];
          let allElements: any[] = [];
          
          // For each page, get its elements
          for (const page of pages) {
            const pageId = page.pageId || page.id;
            if (pageId) {
              try {
                console.log(`Fetching elements for page: ${pageId}`);
                const elementsData = await fetchWithAuth(`/workbooks/${workbookId}/pages/${pageId}/elements`, token);
                console.log(`Elements data for page ${pageId}:`, JSON.stringify(elementsData, null, 2));
                
                const pageElements = elementsData.entries || elementsData || [];
                
                // Add page information to each element
                const elementsWithPageInfo = pageElements.map((element: any) => ({
                  ...element,
                  pageId: pageId,
                  pageName: page.name || page.title || `Page ${pageId}`
                }));
                
                allElements = allElements.concat(elementsWithPageInfo);
              } catch (pageError) {
                console.warn(`Failed to fetch elements for page ${pageId}:`, pageError);
                // Continue with other pages even if one fails
              }
            }
          }
          
          console.log('All extracted elements:', allElements);
          
          transformedData = allElements.map((element: any) => ({
            id: element.elementId || element.id || element.elementUid,
            name: element.name || element.title || element.displayName || `${element.pageName} - ${element.name || element.title || element.displayName || 'Unnamed Element'}`,
            type: element.type || element.elementType || 'element',
            description: element.description || `Element on page: ${element.pageName}`,
            pageId: element.pageId,
            pageName: element.pageName
          }));
          
        } catch (error) {
          console.error('Error fetching workbook elements:', error);
          transformedData = [];
        }
        
        console.log('Final transformed elements data:', transformedData);
        break;

      case 'materializationSchedules':
        const workbookIdForMat = searchParams.get('workbookId');
        if (!workbookIdForMat) {
          return NextResponse.json(
            { error: 'workbookId parameter is required for materializationSchedules' },
            { status: 400 }
          );
        }
        
        try {
          console.log(`Fetching materialization schedules for workbook: ${workbookIdForMat}`);
          const schedulesData = await fetchWithAuth(`/workbooks/${workbookIdForMat}/materialization-schedules`, token);
          console.log('Materialization schedules data:', JSON.stringify(schedulesData, null, 2));
          
          const schedules = schedulesData.entries || schedulesData || [];
          
          transformedData = schedules.map((schedule: any) => ({
            id: schedule.sheetId, // Use sheetId as the value that will be sent to the script
            name: schedule.elementName, // Display the element name to the user
            description: `${schedule.schedule.cronSpec} ${schedule.schedule.timezone}${schedule.paused ? ' - PAUSED' : ''}`,
            type: 'materializationSchedule',
            sheetId: schedule.sheetId,
            elementName: schedule.elementName,
            cronSpec: schedule.schedule.cronSpec,
            timezone: schedule.schedule.timezone,
            paused: schedule.paused
          }));
          
        } catch (error) {
          console.error('Error fetching materialization schedules:', error);
          transformedData = [];
        }
        
        console.log('Final transformed schedules data:', transformedData);
        break;

      default:
        return NextResponse.json(
          { error: `Unsupported resource type: ${type}` },
          { status: 400 }
        );
    }

    return NextResponse.json({
      type,
      count: transformedData.length,
      data: transformedData.sort((a: any, b: any) => (a.name || '').localeCompare(b.name || ''))
    });

  } catch (error) {
    console.error('Error in resources API:', error);
    return NextResponse.json(
      { error: 'Failed to fetch resources' },
      { status: 500 }
    );
  }
}
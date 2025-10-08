import { Injectable } from '@angular/core';
import { client } from '@sigmacomputing/plugin';

@Injectable({
    providedIn: 'root',
})

export class PluginService {

    getPluginInstance() {
        return client;
    }
    
}